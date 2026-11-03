"""Business-signal discovery for one company from public sources:
careers page (hiring), company news/blog page, and public news RSS. Rule-based classification with
optional AI verification. Every signal keeps its source URL and publication date (if known)."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.ai.sanitize import wrap_untrusted
from app.discovery.normalize import name_key
from app.discovery.providers.base import ProviderError
from app.discovery.providers.public_sources import classify_signal_text, news_rss_items
from app.models import Company
from app.research.extractor import PageData
from app.services.signals import save_signal

log = logging.getLogger(__name__)
SENIOR_ROLE = re.compile(r"\b(head of|director|vp|vice president|chief|cto|cmo|coo|cio|lead)\b", re.I)
JOB_TITLE = re.compile(
    r"\b(engineer|developer|designer|manager|marketing|sales|account executive|analyst|operations|product|"
    r"head of|director|lead|specialist|coordinator|recruiter|scientist|consultant|support)\b", re.I)
DIGITAL_ROLES = re.compile(r"\b(marketing|brand|growth|digital|web|content|design|ux|ui|product marketing)\b", re.I)
KNOWLEDGE_ROLES = re.compile(r"\b(operations|knowledge|enablement|it |information|internal tools|data|"
                             r"chief of staff|people ops|program manager)\b", re.I)


def careers_signals(page: PageData) -> list[dict[str, Any]]:
    titles = []
    for h in page.headings:
        t = h["text"]
        if JOB_TITLE.search(t) and len(t) < 90:
            titles.append(t)
    for lk in page.internal_links + [{"url": u, "text": ""} for u in page.external_links]:
        t = lk.get("text") or ""
        if JOB_TITLE.search(t) and len(t) < 90 and t not in titles:
            titles.append(t)
    titles = list(dict.fromkeys(titles))[:40]
    if not titles:
        return []
    senior = [t for t in titles if SENIOR_ROLE.search(t)]
    digital = [t for t in titles if DIGITAL_ROLES.search(t)]
    knowledge = [t for t in titles if KNOWLEDGE_ROLES.search(t)]
    desc = f"Careers page lists {len(titles)} role-like openings"
    if senior:
        desc += f", including senior roles: {', '.join(senior[:3])}"
    return [{
        "signal_type": "hiring", "description": desc + ".", "source_url": page.final_url,
        "evidence": "; ".join(titles[:12]), "confidence": 0.65, "published_at": None,
        "data": {"roles": titles, "senior_roles": senior, "digital_roles": digital, "ops_knowledge_roles": knowledge,
                 "tools_mentioned": page.tools_mentioned},
    }]


def news_signals(db: Session, company: Company, lookback_days: int, use_ai: bool, job_id=None) -> list[dict[str, Any]]:
    q = f'"{company.name}"'
    if company.domain_normalized:
        q += f" OR \"{company.domain_normalized}\""
    try:
        items = news_rss_items(q, limit=25)
    except (ProviderError, Exception) as e:  # noqa: BLE001
        log.info("news rss failed for %s: %s", company.name, e)
        return []
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    key = name_key(company.name)
    candidates = []
    for i, it in enumerate(items):
        if it["published_at"] and it["published_at"] < cutoff:
            continue
        title = it["title"]
        # strict mention check: company name or domain must appear in the headline
        if key and key not in name_key(title) and (company.domain_normalized or "~") not in title.lower():
            continue
        candidates.append({**it, "id": f"N{i}"})
    out: list[dict[str, Any]] = []
    classified: dict[str, Any] = {}
    if use_ai and candidates:
        classified = _ai_classify(db, company, candidates, job_id)
    for c in candidates:
        ai = classified.get(c["id"])
        if ai is not None:
            if not ai.about_this_company or ai.signal_type == "none":
                continue
            stype, desc, conf, method = ai.signal_type, ai.description, min(0.85, ai.confidence), "llm"
        else:
            stype = classify_signal_text(c["title"])
            if not stype:
                continue
            # Unverified headline match (name collisions are common) — kept for review, not used for scoring.
            desc, conf, method = c["title"], 0.3, "rule_unverified"
        out.append({"signal_type": stype, "description": desc, "source_url": c["link"],
                    "published_at": c["published_at"], "evidence": c["title"], "confidence": conf,
                    "source_name": c.get("source_name"), "method": method})
    return out


def _ai_classify(db: Session, company: Company, items: list[dict], job_id) -> dict[str, Any]:
    from app.ai.agents.schemas import BusinessSignalOutput
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, load_prompt, run_agent

    body = "\n".join(f"[{c['id']}] {c['title']} ({c.get('source_name') or ''}, "
                     f"{c['published_at'].date() if c['published_at'] else 'undated'})" for c in items)
    user = (f"Company: {company.name} (domain: {company.domain_normalized})\n"
            f"Classify each item:\n{wrap_untrusted(body, source='news_rss', kind='news_headlines')}")
    try:
        res = run_agent(db, agent="business_signal", system=load_prompt("business_signals"), user=user,
                        schema=BusinessSignalOutput, tier="fast", company_id=company.id, job_id=job_id)
    except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
        log.info("signal agent skipped: %s", e)
        return {}
    valid_ids = {c["id"] for c in items}
    return {it.item_id: it for it in res.output.items if it.item_id in valid_ids}


def store_signals(db: Session, company: Company, signals: list[dict[str, Any]], rcfg: dict) -> int:
    n = 0
    for s in signals:
        _, created = save_signal(
            db, company, signal_type=s["signal_type"], description=s["description"], source_url=s["source_url"],
            published_at=s.get("published_at"), evidence=s.get("evidence"), confidence=s.get("confidence", 0.5),
            source_name=s.get("source_name"), method=s.get("method", "rule"), data=s.get("data"),
            fresh_days=rcfg["fresh_signal_days"], recent_days=rcfg["recent_signal_days"])
        n += int(created)
    return n
