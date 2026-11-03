"""Discovery engine: builds queries from campaign config, enforces quotas, runs providers, normalises,
deduplicates and saves companies with provenance."""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.discovery.normalize import name_key
from app.discovery.providers import WEB_SEARCH_KEYS, get_provider
from app.discovery.providers.base import (
    DiscoveredCompany,
    DiscoveryQuery,
    ProviderError,
    ProviderNotConfigured,
)
from app.models import Campaign, Company, SearchQuery
from app.services import settings_service
from app.services.companies import upsert_company
from app.services.signals import save_signal
from app.services.suppression import is_suppressed

log = logging.getLogger(__name__)

DEFAULT_TEMPLATES: dict[str, list[str]] = {
    "funding": ["{industry} startup raises seed OR \"series A\" {year} {geo}",
                "recently funded {industry} company {geo}"],
    "hiring": ["{industry} company hiring \"head of marketing\" {geo}",
               "{industry} company hiring \"head of operations\" OR CTO {geo}"],
    "product_launch": ["{industry} company launches new product {year} {geo}"],
    "expansion": ["{industry} company expands into {geo} {year}"],
    "digital_transformation": ["{industry} company digital transformation initiative {geo}"],
    "growth": ["fast growing {industry} company {geo} {year}"],
}
DEFAULT_SOURCES = ["yc_directory", "hn_hiring"]


@dataclass
class DiscoveryStats:
    queries: int = 0
    results: int = 0
    new_companies: int = 0
    duplicates: int = 0
    suppressed: int = 0
    signals: int = 0
    errors: list[str] = field(default_factory=list)
    limited_mode: bool = False
    notes: list[str] = field(default_factory=list)
    company_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def build_queries(campaign: Campaign, max_queries: int) -> list[str]:
    templates = list(campaign.query_templates or [])
    if not templates:
        for focus in campaign.signal_focus or ["funding", "growth"]:
            templates += DEFAULT_TEMPLATES.get(focus, [])
        if not templates:
            templates = DEFAULT_TEMPLATES["growth"]
    industries = campaign.industries or [""]
    geos = campaign.geographies or [""]
    roles = campaign.target_roles or [""]
    keywords = campaign.keywords or [""]
    year = datetime.now(UTC).year
    out: list[str] = []
    for t, ind, geo, role, kw in itertools.product(templates, industries, geos, roles[:1], keywords[:1]):
        q = t.format(industry=ind, geo=geo, role=role, keyword=kw, year=year)
        q = " ".join(q.split())
        if q and q not in out:
            out.append(q)
        if len(out) >= max_queries:
            break
    return out


def searches_today(db: Session, providers: list[str]) -> int:
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count()).select_from(SearchQuery).where(
        SearchQuery.provider.in_(providers), SearchQuery.created_at >= since, SearchQuery.status != "limited")) or 0


def companies_created_today(db: Session, campaign_id) -> int:
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count()).select_from(Company).where(
        Company.campaign_id == campaign_id, Company.created_at >= since)) or 0


def _offset_for(db: Session, campaign_id, provider: str, query_text: str) -> int:
    """Advance through result pages across runs so scheduled discovery finds new companies."""
    total = db.scalar(select(func.coalesce(func.sum(SearchQuery.result_count), 0)).where(
        SearchQuery.campaign_id == campaign_id, SearchQuery.provider == provider, SearchQuery.query == query_text,
        SearchQuery.status == "ok", SearchQuery.created_at >= datetime.now(UTC) - timedelta(days=90)))
    return int(total or 0)


def run_discovery(
    db: Session,
    campaign: Campaign,
    *,
    trigger: str = "manual",
    job_id=None,
    sources: list[str] | None = None,
    manual_query: str | None = None,
    limit_override: int | None = None,
) -> DiscoveryStats:
    cfg = settings_service.get_section(db, "discovery")
    rcfg = settings_service.get_section(db, "research")
    stats = DiscoveryStats()
    sources = sources or list(campaign.sources or []) or list(DEFAULT_SOURCES)
    web_provider = cfg.get("web_search_provider", "none")
    if web_provider != "none" and web_provider not in sources and not campaign.sources:
        sources.append(web_provider)
    if campaign.rss_feeds and "rss" not in sources:
        sources.append("rss")

    web_configured = web_provider != "none" and get_provider(web_provider).is_configured(cfg)
    if not web_configured:
        stats.limited_mode = True
        stats.notes.append("Limited mode: no web search provider is configured. Discovery uses public "
                           "directories, hiring threads and RSS feeds only.")

    remaining = (limit_override or campaign.daily_company_limit) - (
        0 if limit_override else companies_created_today(db, campaign.id))
    if remaining <= 0:
        stats.notes.append(f"Daily company limit ({campaign.daily_company_limit}) reached for this campaign.")
        return stats

    base_q = DiscoveryQuery(
        text=manual_query or "", industries=list(campaign.industries or []),
        geographies=list(campaign.geographies or []), company_sizes=list(campaign.company_sizes or []),
        keywords=list(campaign.keywords or []), signal_focus=list(campaign.signal_focus or []),
        params={"rss_feeds": list(campaign.rss_feeds or [])},
    )
    batch_seen: set[str] = set()

    for key in sources:
        if remaining <= 0:
            break
        try:
            provider = get_provider(key)
        except KeyError:
            stats.errors.append(f"Unknown provider {key}")
            continue
        if not provider.is_configured(cfg):
            stats.notes.append(f"{provider.label}: not configured — skipped.")
            if key in WEB_SEARCH_KEYS:
                stats.limited_mode = True
            continue
        if key in WEB_SEARCH_KEYS:
            quota = int(cfg.get("daily_search_quota", 100))
            used = searches_today(db, WEB_SEARCH_KEYS)
            texts = [manual_query] if manual_query else build_queries(campaign, campaign.daily_query_limit)
            for text in texts:
                if used >= quota:
                    stats.notes.append(f"Daily web-search quota ({quota}) reached.")
                    break
                q = DiscoveryQuery(**{**base_q.__dict__, "text": text, "params": dict(base_q.params)})
                q.limit = min(int(cfg.get("results_per_query", 10)), remaining)
                remaining -= _run_one(db, provider, q, campaign, trigger, job_id, cfg, rcfg, stats, batch_seen)
                used += 1
        else:
            q = DiscoveryQuery(**{**base_q.__dict__, "params": dict(base_q.params)})
            q.limit = min(remaining, 25)
            q.offset = _offset_for(db, campaign.id, key, provider.describe_query(q))
            remaining -= _run_one(db, provider, q, campaign, trigger, job_id, cfg, rcfg, stats, batch_seen)
    return stats


def _run_one(db, provider, q: DiscoveryQuery, campaign: Campaign, trigger, job_id, cfg, rcfg,
             stats: DiscoveryStats, batch_seen: set[str]) -> int:
    sq = SearchQuery(campaign_id=campaign.id, job_id=job_id, provider=provider.key,
                     query=provider.describe_query(q), trigger=trigger,
                     params={"offset": q.offset, "limit": q.limit, "industries": q.industries,
                             "geographies": q.geographies, "sizes": q.company_sizes})
    db.add(sq)
    db.flush()
    stats.queries += 1
    try:
        found = provider.search(q, cfg)
    except ProviderNotConfigured as e:
        sq.status, sq.error = "limited", str(e)
        stats.notes.append(str(e))
        return 0
    except ProviderError as e:
        sq.status, sq.error = "error", str(e)
        stats.errors.append(f"{provider.key}: {e}")
        return 0
    except Exception as e:  # noqa: BLE001 - provider bugs/transient network must not kill the run
        log.exception("provider %s failed", provider.key)
        sq.status, sq.error = "error", f"{type(e).__name__}: {e}"
        stats.errors.append(f"{provider.key}: {type(e).__name__}")
        return 0
    leftovers = q.params.pop("_leftovers", [])
    if leftovers:
        extracted = ai_extract_companies(db, leftovers, job_id)
        if extracted:
            stats.notes.append(f"Discovery Agent extracted {len(extracted)} companies from news/article results.")
        found = found + extracted
    sq.status = "ok"
    sq.result_count = len(found)
    sq.results = [{"name": c.name, "domain": c.domain, "url": c.source_url} for c in found][:50]
    stats.results += len(found)
    new = 0
    for item in found:
        new += _save_discovered(db, item, provider.key, provider.kind, campaign, sq, rcfg, stats, batch_seen)
    sq.new_companies = new
    return new


def _save_discovered(db: Session, item: DiscoveredCompany, provider_key: str, kind: str, campaign: Campaign,
                     sq: SearchQuery, rcfg: dict, stats: DiscoveryStats, batch_seen: set[str]) -> int:
    if not item.name and not item.domain:
        return 0
    key = item.domain or name_key(item.name)
    nk = name_key(item.name)
    if key in batch_seen or (nk and nk in batch_seen):
        stats.duplicates += 1
        return 0
    batch_seen.update({key, nk} - {""})
    if is_suppressed(db, domain=item.domain):
        stats.suppressed += 1
        return 0
    res = upsert_company(
        db, name=item.name, domain=item.domain, website=item.website, campaign_id=campaign.id,
        fields={"industry": item.industry, "location": item.location, "country": item.country,
                "size_range": item.size_range, "description": item.description,
                "data": {"discovery": {provider_key: item.raw}}},
        source={"provider": provider_key, "source_type": kind, "source_url": item.source_url,
                "title": item.source_title, "snippet": item.snippet, "search_query_id": sq.id,
                "raw": item.to_json()},
    )
    for s in item.signals:
        _, created = save_signal(db, res.company, signal_type=s.signal_type, description=s.description,
                                 source_url=s.source_url, published_at=s.published_at, evidence=s.evidence,
                                 confidence=s.confidence, source_name=provider_key,
                                 fresh_days=rcfg["fresh_signal_days"], recent_days=rcfg["recent_signal_days"])
        stats.signals += int(created)
    if res.created:
        stats.new_companies += 1
        stats.company_ids.append(str(res.company.id))
        return 1
    stats.duplicates += 1
    return 0


def ai_extract_companies(db: Session, results: list[dict], job_id=None) -> list[DiscoveredCompany]:
    """Discovery Agent: pull companies that are the subject of news/article search results.

    Validation: the evidence quote must appear in that result's text, and a website is only accepted if
    its domain literally appears in the result. Companies without a verifiable domain are not saved."""
    from app.ai.agents.schemas import DiscoveryOutput
    from app.ai.llm.providers import llm_available
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, load_prompt, run_agent
    from app.ai.sanitize import wrap_untrusted
    from app.discovery.normalize import normalize_domain
    from app.discovery.providers.base import DiscoveredSignal
    from app.research.evidence import quote_in

    if not llm_available(settings_service.get_section(db, "llm")):
        return []
    items = {f"R{i}": r for i, r in enumerate(results[:20])}
    body = "\n".join(f"[{rid}] {r.get('title', '')} — {r.get('snippet', '')} ({r.get('url', '')})"
                      for rid, r in items.items())
    try:
        res = run_agent(db, agent="discovery", system=load_prompt("discovery"),
                        user=wrap_untrusted(body, source="search_results", kind="search_results"),
                        schema=DiscoveryOutput, tier="fast", job_id=job_id)
    except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
        log.info("discovery agent skipped: %s", e)
        return []
    out = []
    for c in res.output.companies:
        r = items.get(c.result_id)
        if r is None:
            continue
        text = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}"
        if not quote_in(c.evidence_quote, text) or not quote_in(c.name, text):
            continue
        domain = normalize_domain(c.website) if c.website else None
        if not domain or domain not in text.lower():
            continue
        sig = [DiscoveredSignal(c.signal_type, (r.get("title") or "")[:300], r.get("url") or "", None,
                                c.evidence_quote, 0.5)] if c.signal_type and r.get("url") else []
        out.append(DiscoveredCompany(name=c.name, domain=domain, website=f"https://{domain}",
                                     source_url=r.get("url"), source_title=r.get("title"), snippet=r.get("snippet"),
                                     signals=sig, raw={"extracted_by": "discovery_agent"}))
    return out
