"""The seven business workflows (+ maintenance). Each is idempotent: it selects the items that still
need work based on persisted state, so re-running after a failure continues where it stopped."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.models import Campaign
from app.workflows.engine import JobContext, start_job, workflow


def _ids(values: list[Any] | None) -> list[uuid.UUID]:
    return [uuid.UUID(str(v)) for v in (values or [])]


# ------------------------------------------------------------------------------------ 1 discovery
@workflow("discovery", "Run configured searches, normalise, deduplicate, save companies, queue research.")
def discovery_workflow(ctx: JobContext) -> dict[str, Any]:
    from app.discovery.engine import run_discovery

    db = ctx.db
    p = ctx.params
    if p.get("campaign_id"):
        campaigns = [db.get(Campaign, uuid.UUID(p["campaign_id"]))]
    else:
        campaigns = db.scalars(select(Campaign).where(Campaign.is_active.is_(True), Campaign.deleted_at.is_(None))).all()
    campaigns = [c for c in campaigns if c is not None]
    if not campaigns:
        ctx.log("No active campaigns — nothing to discover.")
        return {"campaigns": 0}
    totals: dict[str, Any] = {"campaigns": 0, "new_companies": 0, "results": 0, "queries": 0, "duplicates": 0,
                              "signals": 0, "limited_mode": False, "notes": []}
    for c in campaigns:
        ctx.check()
        stats = run_discovery(db, c, trigger=ctx.job.trigger, job_id=ctx.job.id, sources=p.get("sources"),
                              manual_query=p.get("query"), limit_override=p.get("limit"))
        db.commit()
        totals["campaigns"] += 1
        for k in ("new_companies", "results", "queries", "duplicates", "signals"):
            totals[k] += getattr(stats, k)
        totals["limited_mode"] = totals["limited_mode"] or stats.limited_mode
        totals["notes"] = list(dict.fromkeys(totals["notes"] + stats.notes))
        for e in stats.errors:
            ctx.error(e, campaign=str(c.id))
        ctx.log(f"Campaign '{c.name}': {stats.new_companies} new companies from {stats.results} results",
                notes=stats.notes)
        if c.auto_research and stats.company_ids and p.get("chain", True):
            start_job(db, "research", params={"company_ids": stats.company_ids, "chain": True}, trigger="chained",
                      parent_id=ctx.job.id, campaign_id=c.id)
    return totals


def _select_companies(ctx: JobContext, statuses, order_col=None, extra=None) -> list:
    from app.models import Company

    db, p = ctx.db, ctx.params
    if p.get("company_ids"):
        rows = db.scalars(select(Company).where(Company.id.in_(_ids(p["company_ids"])),
                                                Company.deleted_at.is_(None))).all()
        return list(rows)
    stmt = select(Company).where(Company.deleted_at.is_(None), Company.status.in_(statuses))
    if extra is not None:
        stmt = stmt.where(extra)
    stmt = stmt.order_by(order_col if order_col is not None else Company.created_at).limit(int(p.get("batch_size", 10)))
    return list(db.scalars(stmt).all())


def _per_company(ctx: JobContext, companies, fn, label: str) -> dict[str, Any]:
    """Run fn(company) for each company with per-item error isolation."""
    ok, failed, done_ids = 0, 0, []
    for c in companies:
        ctx.check()
        try:
            with ctx.db.begin_nested():
                fn(c)
            ctx.db.commit()
            ok += 1
            done_ids.append(str(c.id))
        except Exception as e:  # noqa: BLE001 - isolate failures per company
            ctx.db.rollback()
            failed += 1
            ctx.error(f"{label} failed for {c.name}: {type(e).__name__}: {e}", company_id=str(c.id))
    return {"processed": ok, "failed": failed, "company_ids": done_ids}


# ------------------------------------------------------------------------------------ 2 research
@workflow("research", "Fetch websites, extract information, discover signals, generate research reports.")
def research_workflow(ctx: JobContext) -> dict[str, Any]:
    from app.models import LeadStatus
    from app.research.service import research_company

    force = bool(ctx.params.get("force"))
    companies = _select_companies(ctx, [LeadStatus.NEW])
    ctx.log(f"Researching {len(companies)} companies")

    def run(c):
        r = research_company(ctx.db, c, job_id=ctx.job.id, force=force)
        ctx.log(f"{c.name}: report v{r.version} ({r.status}), {len(r.pages)} pages")

    stats = _per_company(ctx, companies, run, "research")
    if ctx.params.get("chain") and stats["company_ids"]:
        start_job(ctx.db, "contacts", params={"company_ids": stats["company_ids"], "chain": True},
                  trigger="chained", parent_id=ctx.job.id)
    return stats


# ------------------------------------------------------------------------------------ 3 contacts
@workflow("contacts", "Find decision-makers and public business contact details; check email status.")
def contacts_workflow(ctx: JobContext) -> dict[str, Any]:
    from app.models import Company, LeadStatus
    from app.research.contact_service import find_contacts

    companies = _select_companies(ctx, [LeadStatus.RESEARCHED, LeadStatus.QUALIFIED],
                                  extra=Company.last_contacts_at.is_(None))
    totals = {"people": 0, "emails_published": 0}

    def run(c):
        s = find_contacts(ctx.db, c, job_id=ctx.job.id)
        totals["people"] += s["candidates"]
        totals["emails_published"] += s["emails_published"]
        ctx.log(f"{c.name}: {s['candidates']} people, {s['emails_published']} published emails")

    stats = _per_company(ctx, companies, run, "contacts")
    if ctx.params.get("chain") and stats["company_ids"]:
        start_job(ctx.db, "qualification", params={"company_ids": stats["company_ids"], "chain": True},
                  trigger="chained", parent_id=ctx.job.id)
    return {**stats, **totals}


# ------------------------------------------------------------------------------------ 4 qualification
@workflow("qualification", "Score website and Company Brain opportunities, pick the best offer, queue qualified leads.")
def qualification_workflow(ctx: JobContext) -> dict[str, Any]:
    from app.models import LeadStatus
    from app.services.orchestrator import write_brief
    from app.services.scoring import score_company

    companies = _select_companies(ctx, [LeadStatus.RESEARCHED])
    recs: dict[str, int] = {}

    def run(c):
        opp = score_company(ctx.db, c, job_id=ctx.job.id)
        recs[opp.recommended_service] = recs.get(opp.recommended_service, 0) + 1
        write_brief(ctx.db, c, job_id=ctx.job.id)
        ctx.log(f"{c.name}: website {opp.website_score} / brain {opp.brain_score} → {opp.recommended_service}")

    stats = _per_company(ctx, companies, run, "qualification")
    if ctx.params.get("chain") and stats["company_ids"]:
        start_job(ctx.db, "drafting", params={"company_ids": stats["company_ids"]}, trigger="chained",
                  parent_id=ctx.job.id)
    return {**stats, "recommendations": recs}


# ------------------------------------------------------------------------------------ 5 drafting
@workflow("drafting", "Generate personalised messages, validate facts, run quality checks, queue for approval.")
def drafting_workflow(ctx: JobContext) -> dict[str, Any]:
    from app.ai.runtime import AgentUnavailable, BudgetExceeded
    from app.models import LeadStatus
    from app.services.outreach import OutreachBlocked, generate_draft

    companies = _select_companies(ctx, [LeadStatus.QUALIFIED], order_col=None)
    stats = {"drafted": 0, "pending_approval": 0, "needs_review": 0, "skipped": 0, "failed": 0, "limited_mode": False}
    for c in companies:
        ctx.check()
        try:
            with ctx.db.begin_nested():
                d = generate_draft(ctx.db, c, job_id=ctx.job.id)
            ctx.db.commit()
            stats["drafted"] += 1
            stats["pending_approval" if d.status.value == "pending_approval" else "needs_review"] += 1
            ctx.log(f"{c.name}: draft v{d.version} quality {d.quality_score} → {d.status.value}")
        except OutreachBlocked as e:
            ctx.db.rollback()
            stats["skipped"] += 1
            ctx.log(f"{c.name}: skipped — {e}")
        except AgentUnavailable as e:
            ctx.db.rollback()
            stats["limited_mode"] = True
            ctx.log(f"Drafting requires an LLM: {e}")
            break
        except BudgetExceeded as e:
            ctx.db.rollback()
            ctx.log(f"Stopping: {e}")
            break
        except Exception as e:  # noqa: BLE001
            ctx.db.rollback()
            stats["failed"] += 1
            ctx.error(f"drafting failed for {c.name}: {type(e).__name__}: {e}", company_id=str(c.id))
    return stats


# ------------------------------------------------------------------------------------ 6 approval
@workflow("approval", "Create unsent mailbox drafts for drafts a human already approved (retries failures).")
def approval_workflow(ctx: JobContext) -> dict[str, Any]:
    """Never approves anything itself: it only processes drafts with status APPROVED (human decision)."""
    from app.integrations.email.base import MailboxAuthError, MailboxError
    from app.integrations.email.service import create_mailbox_draft, default_account
    from app.models import DraftStatus, OutreachDraft

    acct = default_account(ctx.db)
    if acct is None:
        ctx.log("No connected email account — approved drafts are waiting.")
        return {"created": 0, "waiting": True}
    drafts = ctx.db.scalars(select(OutreachDraft).where(OutreachDraft.status == DraftStatus.APPROVED,
                                                        OutreachDraft.approved_by_id.is_not(None))
                            .limit(int(ctx.params.get("batch_size", 20)))).all()
    created, failed = 0, 0
    for d in drafts:
        ctx.check()
        try:
            create_mailbox_draft(ctx.db, d, acct)
            ctx.db.commit()
            created += 1
        except MailboxAuthError as e:
            ctx.db.commit()
            ctx.error(f"Mailbox auth: {e}")
            break
        except (MailboxError, ValueError) as e:
            ctx.db.commit()
            failed += 1
            ctx.error(f"Draft {d.id}: {e}")
    return {"created": created, "failed": failed}


# ------------------------------------------------------------------------------------ 7 replies
@workflow("replies", "Monitor connected mailboxes, match replies to leads, classify, suggest actions.")
def replies_workflow(ctx: JobContext) -> dict[str, Any]:
    from app.models import EmailAccount
    from app.services.replies import sync_account

    stmt = select(EmailAccount).where(EmailAccount.deleted_at.is_(None), EmailAccount.status == "connected")
    if ctx.params.get("account_id"):
        stmt = stmt.where(EmailAccount.id == uuid.UUID(ctx.params["account_id"]))
    totals: dict[str, Any] = {"accounts": 0, "new_replies": 0, "sent_detected": 0}
    for acct in ctx.db.scalars(stmt).all():
        ctx.check()
        s = sync_account(ctx.db, acct, job_id=ctx.job.id)
        ctx.db.commit()
        totals["accounts"] += 1
        totals["new_replies"] += s["new_replies"]
        totals["sent_detected"] += s["sent_detected"]
        if s.get("error"):
            ctx.error(f"{acct.email}: {s['error']}")
        ctx.log(f"{acct.email}: {s}")
    return totals


# ------------------------------------------------------------------------------------ maintenance
@workflow("maintenance", "Apply data-retention settings and housekeeping.")
def maintenance_workflow(ctx: JobContext) -> dict[str, Any]:
    from app.services.retention import run_retention

    return run_retention(ctx.db)
