"""Company research: crawl → extract → measurable audit → signals → AI analysis → validated report."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.sanitize import wrap_untrusted
from app.core import http as core_http
from app.discovery.normalize import normalize_url
from app.models import Company, LeadStatus, ResearchReport
from app.models.base import utcnow
from app.research.evidence import EvidenceSet, quote_in
from app.research.extractor import PageData, extract
from app.research.fetcher import fetch, robots_info
from app.research.signals_research import careers_signals, news_signals, store_signals
from app.research.site_audit import audit_site
from app.services import settings_service
from app.services.state_machine import try_transition

log = logging.getLogger(__name__)
PAGE_PRIORITY = ["about", "services", "pricing", "careers", "team", "contact", "customers", "news"]
SUBJECTIVE_AREAS = {"visual_consistency", "user_experience", "messaging", "brand_positioning", "content_quality",
                    "product_presentation", "navigation", "information_architecture"}


def latest_report(db: Session, company_id) -> ResearchReport | None:
    return db.scalar(select(ResearchReport).where(ResearchReport.company_id == company_id)
                     .order_by(ResearchReport.created_at.desc()).limit(1))


def needs_research(db: Session, company: Company, recrawl_days: int) -> bool:
    if company.last_researched_at is None:
        return True
    return company.last_researched_at < utcnow() - timedelta(days=recrawl_days)


def crawl(db: Session, company: Company, rcfg: dict) -> tuple[list[PageData], list[dict], dict[str, Any]]:
    """Returns (pages, errors, meta)."""
    start = normalize_url(company.website) or (f"https://{company.domain_normalized}" if company.domain_normalized else None)
    errors: list[dict] = []
    meta: dict[str, Any] = {}
    if not start:
        return [], [{"url": None, "error": "Company has no website"}], meta
    max_pages = int(rcfg.get("max_pages", 8))
    delay = float(rcfg.get("request_delay_seconds", 1.5))
    max_age = int(rcfg.get("recrawl_after_days", 14))
    pages: list[PageData] = []
    with core_http.client(timeout=20) as http:
        meta["robots"] = robots_info(start, http)
        home = fetch(db, start, http=http, min_delay=delay, max_age_days=max_age)
        if not home.ok and start.startswith("https://") and (home.blocked_reason or "").startswith("network_error"):
            alt = fetch(db, "http://" + start[8:], http=http, min_delay=delay, max_age_days=max_age)
            if alt.ok:
                home = alt
        if not home.ok:
            errors.append({"url": start, "error": home.blocked_reason or f"HTTP {home.status_code}"})
            return pages, errors, meta
        meta["home_elapsed_ms"] = home.elapsed_ms
        hp = extract(home.html or "", home.url, home.final_url)
        hp.kind, hp.rendered = "home", home.rendered
        pages.append(hp)
        chosen: dict[str, str] = {}
        for kind in PAGE_PRIORITY:
            links = [lk for lk in hp.internal_links if lk.get("kind") == kind]
            links.sort(key=lambda lk: len(lk["url"]))
            if links:
                chosen[kind] = links[0]["url"]
        for kind in PAGE_PRIORITY:
            if len(pages) >= max_pages:
                break
            url = chosen.get(kind)
            if not url or any(p.final_url == url or p.url == url for p in pages):
                continue
            res = fetch(db, url, http=http, min_delay=delay, max_age_days=max_age)
            if not res.ok:
                errors.append({"url": url, "error": res.blocked_reason or f"HTTP {res.status_code}"})
                continue
            pd = extract(res.html or "", res.url, res.final_url)
            pd.kind, pd.rendered = kind, res.rendered
            pages.append(pd)
    return pages, errors, meta


def build_evidence(pages: list[PageData], audit: dict, signals: list[dict]) -> EvidenceSet:
    ev = EvidenceSet()
    for i, p in enumerate(pages, start=1):
        head = " | ".join(h["text"] for h in p.headings[:12])
        text = f"TITLE: {p.title}\nMETA: {p.meta_description}\nHEADINGS: {head}\nNAV: {', '.join(p.nav_items)}\n" \
               f"CTAs: {', '.join(p.ctas)}\n\n{p.text[:6000]}"
        ev.add(f"P{i}", "page", p.final_url, text, title=p.title, page_kind=p.kind)
    for c in audit.get("checks", []):
        ev.add(f"A:{c['id']}", "audit", c["evidence_url"],
               f"{c['label']}: {'pass' if c['passed'] else 'fail' if c['passed'] is False else 'n/a'} (value: {c['value']})")
    for i, s in enumerate(signals, start=1):
        date = s.get("published_at")
        ev.add(f"S{i}", "signal", s["source_url"],
               f"[{s['signal_type']}] {s['description']} (published: {date.date() if date else 'unknown'}, "
               f"freshness: {s.get('freshness', 'unknown')})", signal_id=s.get("id"))
    return ev


def validate_observations(obs: list, ev: EvidenceSet) -> tuple[list[dict], list[dict]]:
    """Downgrade/discard AI observations that are not backed by evidence. Returns (kept, rejected)."""
    kept, rejected = [], []
    for o in obs:
        d = o.model_dump()
        ids = ev.valid_ids(d["evidence_ids"])
        invalid_ids = [i for i in d["evidence_ids"] if i not in ev.items]
        d["evidence_ids"] = ids
        notes = []
        if invalid_ids:
            notes.append(f"dropped unknown evidence ids {invalid_ids}")
        if d["category"] == "verified_fact":
            if not (ids and d.get("quote") and ev.any_quote(d["quote"], ids)):
                # A "fact" whose quote is not in the cited source is treated as fabricated.
                d["validation"] = notes + ["quote not found in cited source → rejected"]
                rejected.append(d)
                continue
            if d["area"] in SUBJECTIVE_AREAS and not d.get("quote"):
                d["category"] = "hypothesis"
        elif d["category"] == "direct_observation":
            if not ids:
                d["category"] = "hypothesis"
                notes.append("no evidence cited → downgraded to hypothesis")
            elif d.get("quote") and not ev.any_quote(d["quote"], ids):
                d["quote"] = None
                notes.append("quote not found → removed")
        if d["area"] == "visual_consistency" and d["category"] in ("verified_fact", "direct_observation"):
            d["category"] = "hypothesis"  # cannot be verified from HTML
        if notes:
            d["validation"] = notes
        kept.append(d)
    return kept, rejected


def ai_analysis(db: Session, company: Company, pages: list[PageData], audit: dict, ev: EvidenceSet, job_id=None):
    from app.ai.agents.context import agency_context
    from app.ai.agents.schemas import WebsiteResearchOutput
    from app.ai.runtime import load_prompt, run_agent

    system = load_prompt("website_research").replace("{agency_context}", agency_context(db, include_knowledge=False))
    blocks = []
    for i, p in enumerate(pages, start=1):
        blocks.append(f"### Page P{i} ({p.kind}) {p.final_url}\n" + wrap_untrusted(
            ev.items[f"P{i}"]["text"], source=p.final_url, max_chars=5000))
    checks = "\n".join(f"A:{c['id']} — {c['label']}: "
                       f"{'pass' if c['passed'] else 'fail' if c['passed'] is False else 'not measurable'}"
                       f" (value: {str(c['value'])[:120]})" for c in audit.get("checks", []))
    user = (f"Company: {company.name} ({company.domain_normalized})\n\nDETERMINISTIC AUDIT CHECKS:\n{checks}\n\n"
            f"Not measurable from HTML: {', '.join(audit.get('not_measured', []))}\n\nPAGES:\n" + "\n\n".join(blocks))
    return run_agent(db, agent="website_research", system=system, user=user, schema=WebsiteResearchOutput,
                     tier="smart", company_id=company.id, job_id=job_id, max_tokens=3000)


def research_company(db: Session, company: Company, *, job_id=None, force: bool = False,
                     use_news: bool | None = None) -> ResearchReport:
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded

    rcfg = settings_service.get_section(db, "research")
    if not force and not needs_research(db, company, int(rcfg["recrawl_after_days"])):
        existing = latest_report(db, company.id)
        if existing:
            return existing
    try_transition(db, company, LeadStatus.RESEARCHING, reason="research started")
    db.flush()
    pages, errors, meta = crawl(db, company, rcfg)
    audit = audit_site(pages, meta)

    # ----- signals
    sig_payloads: list[dict] = []
    for p in pages:
        if p.kind == "careers":
            for s in careers_signals(p):
                s["data"]["observed_at"] = utcnow().isoformat()
                sig_payloads.append(s)
    from app.ai.llm.providers import llm_available

    llm_on = llm_available(settings_service.get_section(db, "llm"))
    if use_news if use_news is not None else rcfg.get("use_news_rss", True):
        sig_payloads += news_signals(db, company, int(rcfg["signal_lookback_days"]), llm_on, job_id)
    store_signals(db, company, sig_payloads, rcfg)
    db.flush()
    from app.models import BuyingSignal

    all_signals = db.scalars(select(BuyingSignal).where(BuyingSignal.company_id == company.id)
                             .order_by(BuyingSignal.published_at.desc().nullslast())).all()
    sig_dicts = [{"id": str(s.id), "signal_type": s.signal_type, "description": s.description,
                  "source_url": s.source_url, "published_at": s.published_at, "freshness": s.freshness}
                 for s in all_signals]
    ev = build_evidence(pages, audit, sig_dicts)

    # ----- business info (deterministic)
    business_info: dict[str, Any] = {
        "public_emails": sorted({e for p in pages for e in p.emails}),
        "phones": sorted({ph for p in pages for ph in p.phones})[:5],
        "social_links": sorted({s for p in pages for s in p.social_links})[:10],
        "tech": audit.get("tech", []),
        "tools_mentioned": audit.get("tools_mentioned", []),
        "json_ld_orgs": [j for p in pages for j in p.json_ld if "Organization" in str(j.get("@type", ""))][:2],
    }
    observations = [{"area": c["area"] if c["area"] in ("accessibility", "mobile_usability") else
                     {"seo": "content_quality", "security": "business", "brand": "brand_positioning",
                      "conversion": "conversion_paths", "content": "content_quality",
                      "performance": "user_experience", "information_architecture": "information_architecture",
                      "mobile": "mobile_usability"}.get(c["area"], "business"),
                     "category": "direct_observation", "text": f"{c['label']}: {'yes' if c['passed'] else 'no'}"
                     + (f" ({c['detail']})" if c.get("detail") else ""), "evidence_ids": [f"A:{c['id']}"],
                     "source": "audit"} for c in audit.get("checks", []) if c["passed"] is not None]
    analysis: dict[str, Any] = {"method": "deterministic"}
    injection_flags = sorted({f for p in pages for f in p.injection_flags})
    summary = None
    if pages and llm_on:
        try:
            res = ai_analysis(db, company, pages, audit, ev, job_id)
            kept, rejected = validate_observations(res.output.observations, ev)
            for k in kept:
                k["source"] = "ai"
            observations += kept
            bi = res.output.business_info.model_dump()
            bi["evidence_ids"] = ev.valid_ids(bi["evidence_ids"])
            business_info["ai"] = bi
            summary = res.output.summary
            analysis = {"method": "llm", "ai_run_id": str(res.run_id), "cached": res.cached,
                        "value_proposition": res.output.value_proposition, "rejected_observations": rejected,
                        "possible_prompt_injection": res.output.possible_prompt_injection}
            if res.output.possible_prompt_injection:
                injection_flags.append("agent_reported_possible_injection")
        except (AgentUnavailable, BudgetExceeded) as e:
            analysis = {"method": "deterministic", "note": str(e)}
        except AgentFailed as e:
            errors.append({"url": None, "error": f"AI analysis failed: {e}"})
            analysis = {"method": "deterministic", "note": "AI analysis failed"}
    if not summary and pages:
        home = pages[0]
        summary = (f"{company.name}: {home.meta_description or home.og.get('description') or home.title}".strip()
                   + " (from site metadata; no AI analysis)")
    if pages and not company.description:
        company.description = (pages[0].meta_description or pages[0].og.get("description") or None)
    if not pages and not observations:
        observations.append({"area": "business", "category": "unknown", "text": "Website could not be retrieved: "
                             + "; ".join(e["error"] for e in errors)[:300], "evidence_ids": [], "source": "system"})

    version = (db.scalar(select(func.max(ResearchReport.version)).where(ResearchReport.company_id == company.id)) or 0) + 1
    status = "complete" if pages and not errors else "partial" if pages else (
        "blocked" if any("robots" in e["error"] or "restricted" in e["error"] or "challenge" in e["error"]
                         for e in errors) else "failed")
    report = ResearchReport(
        company_id=company.id, job_id=job_id, version=version, status=status, summary=summary,
        pages=[{"id": f"P{i}", **{k: v for k, v in p.to_json(text_limit=8000).items()
                                 if k not in ("internal_links", "external_links")},
                "internal_links_count": len(p.internal_links)} for i, p in enumerate(pages, start=1)],
        audit=audit, analysis=analysis, observations=observations, evidence=ev.public(),
        business_info=business_info, robots=meta.get("robots", {}), injection_flags=injection_flags,
        errors=errors, researched_at=utcnow(),
    )
    db.add(report)
    company.last_researched_at = utcnow()
    try_transition(db, company, LeadStatus.RESEARCHED, reason=f"research {status}")
    db.flush()
    return report
