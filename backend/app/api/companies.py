from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api._common import PageParams, apply_sort, get_or_404, like, paginate
from app.core.db import get_db
from app.core.deps import require_operator, require_viewer
from app.discovery.normalize import normalize_domain
from app.models import (
    BuyingSignal,
    Company,
    Contact,
    Interaction,
    LeadScore,
    LeadSource,
    LeadStatus,
    Note,
    Opportunity,
    OutreachDraft,
    ResearchReport,
    Task,
    User,
)
from app.models.base import utcnow
from app.schemas.common import Msg
from app.schemas.crm import (
    BulkAction,
    CompanyIn,
    CompanyOut,
    CompanyPatch,
    ContactOut,
    LeadSourceOut,
    NoteIn,
    NoteOut,
    SignalOut,
    StatusChange,
    TaskOut,
)
from app.services.audit import audit
from app.services.companies import upsert_company
from app.services.csv_io import export_companies
from app.services.state_machine import allowed_targets, transition
from app.services.suppression import is_suppressed, suppress

router = APIRouter(prefix="/api/companies", tags=["companies"])

SORTABLE = {"created_at", "updated_at", "name", "website_score", "brain_score", "last_researched_at", "status"}


def _filtered(q: str | None, status: list[str] | None, campaign_id: uuid.UUID | None, service: str | None,
              min_website: int | None, min_brain: int | None, industry: str | None, tag: str | None):
    stmt = select(Company).where(Company.deleted_at.is_(None))
    if q:
        stmt = stmt.where(or_(Company.name.ilike(like(q)), Company.domain_normalized.ilike(like(q)),
                              Company.industry.ilike(like(q)), Company.location.ilike(like(q))))
    if status:
        stmt = stmt.where(Company.status.in_([LeadStatus(s) for s in status if s in LeadStatus.__members__]))
    if campaign_id:
        stmt = stmt.where(Company.campaign_id == campaign_id)
    if service:
        stmt = stmt.where(Company.recommended_service == service)
    if min_website is not None:
        stmt = stmt.where(Company.website_score >= min_website)
    if min_brain is not None:
        stmt = stmt.where(Company.brain_score >= min_brain)
    if industry:
        stmt = stmt.where(Company.industry.ilike(like(industry)))
    if tag:
        stmt = stmt.where(Company.tags.contains([tag]))
    return stmt


@router.get("")
def list_companies(
    q: str | None = Query(None, max_length=200),
    status: list[str] | None = Query(None),
    campaign_id: uuid.UUID | None = None,
    service: str | None = None,
    min_website: int | None = Query(None, ge=0, le=100),
    min_brain: int | None = Query(None, ge=0, le=100),
    industry: str | None = None,
    tag: str | None = None,
    sort: str | None = None,
    pp: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    stmt = _filtered(q, status, campaign_id, service, min_website, min_brain, industry, tag)
    stmt = apply_sort(stmt, Company, sort, SORTABLE)
    return paginate(db, stmt, pp, lambda c: CompanyOut.model_validate(c))


@router.get("/export")
def export(
    q: str | None = None, status: list[str] | None = Query(None), campaign_id: uuid.UUID | None = None,
    service: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_viewer),
):
    stmt = _filtered(q, status, campaign_id, service, None, None, None, None).order_by(Company.created_at).limit(50_000)
    data = export_companies(db.scalars(stmt).all())
    audit(db, "export.companies", actor=user, detail={"filters": {"q": q, "status": status}})
    db.commit()
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=companies.csv"})


@router.post("", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    domain = normalize_domain(body.website)
    if body.website and not domain:
        raise HTTPException(422, "Website is not a valid domain")
    if is_suppressed(db, domain=domain):
        raise HTTPException(409, "This domain is on the suppression list")
    res = upsert_company(db, name=body.name, domain=domain, website=body.website, campaign_id=body.campaign_id,
                         fields=body.model_dump(exclude={"name", "website", "campaign_id"}),
                         source={"provider": "manual", "source_type": "manual", "title": f"Added by {user.email}"})
    if not res.created:
        raise HTTPException(409, f"Company already exists (matched on {res.matched_on})")
    audit(db, "company.created", actor=user, entity_type="company", entity_id=res.company.id)
    db.commit()
    return res.company


@router.get("/{company_id}")
def company_detail(company_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    c = get_or_404(db, Company, company_id)
    contacts = db.scalars(select(Contact).where(Contact.company_id == c.id, Contact.deleted_at.is_(None))
                          .order_by(Contact.seniority_rank, Contact.created_at)).all()
    sources = db.scalars(select(LeadSource).where(LeadSource.company_id == c.id)
                         .order_by(LeadSource.created_at.desc()).limit(50)).all()
    signals = db.scalars(select(BuyingSignal).where(BuyingSignal.company_id == c.id)
                         .order_by(BuyingSignal.published_at.desc().nullslast())).all()
    report = db.scalar(select(ResearchReport).where(ResearchReport.company_id == c.id)
                       .order_by(ResearchReport.created_at.desc()).limit(1))
    opp = db.scalar(select(Opportunity).where(Opportunity.company_id == c.id))
    scores = db.scalars(select(LeadScore).where(LeadScore.company_id == c.id)
                        .order_by(LeadScore.created_at.desc()).limit(20)).all()
    drafts = db.scalars(select(OutreachDraft).where(OutreachDraft.company_id == c.id, OutreachDraft.deleted_at.is_(None))
                        .order_by(OutreachDraft.created_at.desc())).all()
    interactions = db.scalars(select(Interaction).where(Interaction.company_id == c.id)
                              .order_by(Interaction.occurred_at.desc().nullslast()).limit(100)).all()
    notes = db.scalars(select(Note).where(Note.company_id == c.id, Note.deleted_at.is_(None))
                       .order_by(Note.created_at.desc())).all()
    tasks = db.scalars(select(Task).where(Task.company_id == c.id, Task.deleted_at.is_(None))
                       .order_by(Task.due_at.asc().nullslast())).all()
    from app.api.research import report_summary
    from app.api.drafts import draft_out
    from app.api.opportunities import opp_out

    return {
        "company": CompanyOut.model_validate(c).model_dump(),
        "data": c.data,
        "allowed_transitions": allowed_targets(c.status),
        "disqualified_reason": c.disqualified_reason,
        "contacts": [ContactOut.model_validate(x).model_dump() for x in contacts],
        "sources": [LeadSourceOut.model_validate(x).model_dump() for x in sources],
        "signals": [SignalOut.model_validate(x).model_dump() for x in signals],
        "research": report_summary(report) if report else None,
        "opportunity": opp_out(opp) if opp else None,
        "score_history": [{"service": s.service, "score": s.score, "confidence": s.confidence, "method": s.method,
                           "created_at": s.created_at} for s in scores],
        "drafts": [draft_out(d, brief=True) for d in drafts],
        "interactions": [{"id": i.id, "channel": i.channel, "direction": i.direction, "subject": i.subject,
                          "snippet": i.snippet, "occurred_at": i.occurred_at, "classification": i.classification}
                         for i in interactions],
        "notes": [NoteOut.model_validate(n).model_dump() for n in notes],
        "tasks": [TaskOut.model_validate(t).model_dump() for t in tasks],
    }


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(company_id: uuid.UUID, body: CompanyPatch, db: Session = Depends(get_db),
                   user: User = Depends(require_operator)):
    c = get_or_404(db, Company, company_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(c, k, v)
    audit(db, "company.updated", actor=user, entity_type="company", entity_id=c.id, detail={"fields": list(changes)})
    db.commit()
    return c


@router.post("/{company_id}/status", response_model=CompanyOut)
def change_status(company_id: uuid.UUID, body: StatusChange, db: Session = Depends(get_db),
                  user: User = Depends(require_operator)):
    c = get_or_404(db, Company, company_id)
    try:
        target = LeadStatus(body.status)
    except ValueError:
        raise HTTPException(422, "Unknown status") from None
    if target == LeadStatus.DO_NOT_CONTACT:
        suppress(db, domain=c.domain_normalized, reason="dnc", source=body.reason or "manual", company=c, user=user,
                 block_company=True)
    else:
        transition(db, c, target, actor=user, reason=body.reason)
        if target == LeadStatus.DISQUALIFIED:
            c.disqualified_reason = body.reason
    db.commit()
    return c


@router.delete("/{company_id}", response_model=Msg)
def delete_company(company_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    c = get_or_404(db, Company, company_id)
    c.deleted_at = utcnow()
    for ct in db.scalars(select(Contact).where(Contact.company_id == c.id, Contact.deleted_at.is_(None))):
        ct.deleted_at = utcnow()
    audit(db, "company.deleted", actor=user, entity_type="company", entity_id=c.id)
    db.commit()
    return Msg(message="Company deleted")


@router.post("/bulk")
def bulk(body: BulkAction, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    companies = db.scalars(select(Company).where(Company.id.in_(body.ids), Company.deleted_at.is_(None))).all()
    done, failed = 0, []
    if body.action in ("research", "qualify", "draft"):
        from app.workflows import load_workflows
        from app.workflows.engine import start_job

        load_workflows()
        wf = {"research": "research", "qualify": "qualification", "draft": "drafting"}[body.action]
        job, _ = start_job(db, wf, params={"company_ids": [str(c.id) for c in companies], "force": True}, user=user)
        return {"job_id": str(job.id), "count": len(companies)}
    for c in companies:
        try:
            if body.action == "status":
                target = LeadStatus(body.value)
                if target == LeadStatus.DO_NOT_CONTACT:
                    suppress(db, domain=c.domain_normalized, reason="dnc", source="bulk", company=c, user=user,
                             block_company=True)
                else:
                    transition(db, c, target, actor=user, reason="bulk")
            elif body.action == "tag":
                c.tags = sorted(set(c.tags or []) | {str(body.value)[:60]})
            elif body.action == "untag":
                c.tags = [t for t in (c.tags or []) if t != body.value]
            elif body.action == "campaign":
                c.campaign_id = uuid.UUID(str(body.value)) if body.value else None
            elif body.action == "delete":
                c.deleted_at = utcnow()
            done += 1
        except Exception as e:  # noqa: BLE001
            failed.append({"id": str(c.id), "error": str(e)})
    audit(db, f"company.bulk_{body.action}", actor=user, detail={"count": done, "value": body.value})
    db.commit()
    return {"updated": done, "failed": failed}


@router.post("/{company_id}/notes", response_model=NoteOut, status_code=201)
def add_note(company_id: uuid.UUID, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    c = get_or_404(db, Company, company_id)
    n = Note(company_id=c.id, contact_id=body.contact_id, author_id=user.id, body=body.body)
    db.add(n)
    db.commit()
    return n


@router.delete("/{company_id}/notes/{note_id}", response_model=Msg)
def delete_note(company_id: uuid.UUID, note_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(require_operator)):
    n = get_or_404(db, Note, note_id)
    if n.company_id != company_id:
        raise HTTPException(404, "Note not found")
    n.deleted_at = utcnow()
    db.commit()
    return Msg(message="Note deleted")
