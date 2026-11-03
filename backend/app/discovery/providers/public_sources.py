"""Public, key-free discovery sources.

* Wikidata (CC0 structured data, official SPARQL endpoint) — companies by industry/country with an
  official website.
* YC company directory (public JSON mirror: yc-oss.github.io) — funded startups with website,
  industry, regions, team size, batch and hiring flag.
* Hacker News "Who is hiring?" threads (official Algolia HN API) — companies publicly hiring.
* RSS / Atom feeds (user-configured) — funding/hiring/launch announcements; company websites are
  taken from item links when the link points to a company domain.
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import feedparser

from app.core.config import get_settings
from app.core.http import client, request_with_retry
from app.discovery.normalize import clean_company_name, company_name_from_title, normalize_domain
from app.discovery.providers.base import (
    DiscoveredCompany,
    DiscoveredSignal,
    DiscoveryProvider,
    DiscoveryQuery,
    ProviderError,
    size_bucket,
    size_matches,
)

log = logging.getLogger(__name__)


# ============================================================================ Wikidata
class WikidataProvider(DiscoveryProvider):
    key = "wikidata"
    label = "Wikidata company graph"
    kind = "directory"
    description = "Open company data (industry, country, official website, employees). No key required."

    SPARQL = "https://query.wikidata.org/sparql"
    API = "https://www.wikidata.org/w/api.php"
    requires_auth = False

    def is_configured(self, cfg: dict[str, Any]) -> bool:
        # Wikimedia's User-Agent policy requires contact details; requests without them get HTTP 403.
        return bool(get_settings().crawler_contact)

    def status(self, cfg):
        st = super().status(cfg)
        if st.status == "not_configured":
            st.detail = "Set CRAWLER_CONTACT (URL or email) — required by Wikimedia's User-Agent policy."
        return st

    def _resolve(self, text: str, limit: int = 2) -> list[str]:
        r = request_with_retry(
            "GET", self.API, params={"action": "wbsearchentities", "search": text, "language": "en",
                                     "format": "json", "type": "item", "limit": limit}, retries=2)
        if r.status_code != 200:
            return []
        return [h["id"] for h in r.json().get("search", [])]

    def search(self, q: DiscoveryQuery, cfg: dict[str, Any]) -> list[DiscoveredCompany]:
        if not self.is_configured(cfg):
            raise ProviderError("Wikidata requires CRAWLER_CONTACT to be set (Wikimedia User-Agent policy)")
        industries = q.industries or ([q.text] if q.text else [])
        if not industries:
            raise ProviderError("Wikidata discovery needs at least one industry")
        ind_ids: list[str] = []
        for ind in industries[:4]:
            ind_ids += self._resolve(ind, 2)
            if "industry" not in ind.lower():
                ind_ids += self._resolve(f"{ind} industry", 1)
        if not ind_ids:
            return []
        country_ids: list[str] = []
        for g in q.geographies[:4]:
            country_ids += self._resolve(g, 1)
        values = " ".join(f"wd:{i}" for i in dict.fromkeys(ind_ids))
        country_filter = ""
        if country_ids:
            country_filter = "VALUES ?country { " + " ".join(f"wd:{c}" for c in country_ids) + " } ?c wdt:P17 ?country ."
        query = f"""
SELECT ?c ?cLabel ?website ?countryLabel ?indLabel ?employees ?inception ?hqLabel ?desc WHERE {{
  VALUES ?ind {{ {values} }}
  ?c wdt:P452 ?ind ; wdt:P856 ?website .
  {country_filter}
  OPTIONAL {{ ?c wdt:P17 ?country . }}
  OPTIONAL {{ ?c wdt:P1128 ?employees . }}
  OPTIONAL {{ ?c wdt:P571 ?inception . }}
  OPTIONAL {{ ?c wdt:P159 ?hq . }}
  OPTIONAL {{ ?c schema:description ?desc . FILTER(LANG(?desc) = "en") }}
  FILTER NOT EXISTS {{ ?c wdt:P576 ?dissolved . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY ?c LIMIT {max(1, q.limit * 3)} OFFSET {q.offset}"""
        r = request_with_retry("GET", self.SPARQL, params={"query": query, "format": "json"}, timeout=60,
                               headers={"Accept": "application/sparql-results+json"}, retries=2)
        if r.status_code != 200:
            raise ProviderError(f"Wikidata SPARQL returned HTTP {r.status_code}")
        seen: set[str] = set()
        out: list[DiscoveredCompany] = []
        for b in r.json().get("results", {}).get("bindings", []):
            website = b.get("website", {}).get("value")
            domain = normalize_domain(website)
            if not domain or domain in seen:
                continue
            employees = _num(b.get("employees", {}).get("value"))
            if not size_matches(employees, q.company_sizes):
                continue
            name = b.get("cLabel", {}).get("value", "")
            if re.fullmatch(r"Q\d+", name):
                continue
            seen.add(domain)
            qid_url = b["c"]["value"]
            out.append(DiscoveredCompany(
                name=clean_company_name(name), domain=domain, website=website,
                industry=b.get("indLabel", {}).get("value"),
                location=b.get("hqLabel", {}).get("value"), country=b.get("countryLabel", {}).get("value"),
                size_range=size_bucket(employees), description=b.get("desc", {}).get("value"),
                source_url=qid_url, source_title=f"Wikidata: {name}",
                snippet=b.get("desc", {}).get("value"),
                raw={"employees": employees, "inception": b.get("inception", {}).get("value")},
            ))
            if len(out) >= q.limit:
                break
        return out


def _num(v: Any) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


# ============================================================================ YC directory
_YC_CACHE: dict[str, Any] = {"at": 0.0, "data": None}


class YCDirectoryProvider(DiscoveryProvider):
    key = "yc_directory"
    label = "Y Combinator company directory"
    kind = "directory"
    description = "Venture-funded startups (public directory mirror). Includes hiring flag, team size, regions."
    URL = "https://yc-oss.github.io/api/companies/all.json"

    def _load(self) -> list[dict]:
        if _YC_CACHE["data"] is None or time.time() - _YC_CACHE["at"] > 6 * 3600:
            r = request_with_retry("GET", self.URL, timeout=60, retries=2)
            if r.status_code != 200:
                raise ProviderError(f"YC directory returned HTTP {r.status_code}")
            _YC_CACHE.update(at=time.time(), data=r.json())
        return _YC_CACHE["data"]

    def search(self, q: DiscoveryQuery, cfg: dict[str, Any]) -> list[DiscoveredCompany]:
        data = self._load()
        inds = [i.lower() for i in q.industries]
        geos = [g.lower() for g in q.geographies]
        kws = [k.lower() for k in q.keywords + ([q.text] if q.text else [])]
        min_year = int(q.params.get("min_batch_year", 0) or 0)
        hiring_only = bool(q.params.get("hiring_only") or "hiring" in q.signal_focus)

        def matches(c: dict) -> bool:
            if c.get("status") != "Active" or not c.get("website"):
                return False
            hay_ind = " ".join([c.get("industry") or "", c.get("subindustry") or "", *c.get("industries", []),
                                *c.get("tags", [])]).lower()
            if inds and not any(i in hay_ind for i in inds):
                return False
            hay_geo = " ".join([c.get("all_locations") or "", *c.get("regions", [])]).lower()
            if geos and not any(g in hay_geo for g in geos):
                return False
            if kws:
                hay = (hay_ind + " " + (c.get("one_liner") or "") + " " + (c.get("long_description") or "")).lower()
                if not any(k in hay for k in kws):
                    return False
            if not size_matches(c.get("team_size"), q.company_sizes):
                return False
            if hiring_only and not c.get("isHiring"):
                return False
            if min_year and _batch_year(c.get("batch")) < min_year:
                return False
            return True

        hits = [c for c in data if matches(c)]
        hits.sort(key=lambda c: (-(_batch_year(c.get("batch")) or 0), c.get("id", 0)))  # most recent first
        out: list[DiscoveredCompany] = []
        for c in hits[q.offset: q.offset + q.limit]:
            domain = normalize_domain(c["website"])
            if not domain:
                continue
            signals = []
            if c.get("isHiring"):
                signals.append(DiscoveredSignal("hiring", f"{c['name']} is listed as hiring on its YC directory profile.",
                                                c.get("url") or self.URL, None, "isHiring=true", 0.6))
            year = _batch_year(c.get("batch"))
            if year and year >= datetime.now(UTC).year - 1:
                # Approximate batch start month (YC batches: Winter=Jan, Spring=Apr, Summer=Jun, Fall=Sep).
                season = (c.get("batch") or "").split()[0].lower()
                month = {"winter": 1, "spring": 4, "summer": 6, "fall": 9}.get(season, 1)
                signals.append(DiscoveredSignal(
                    "funding", f"{c['name']} is part of Y Combinator's {c.get('batch')} batch (accelerator investment; "
                    "date approximate).", c.get("url") or self.URL, datetime(year, month, 1, tzinfo=UTC),
                    f"batch={c.get('batch')}", 0.7))
            out.append(DiscoveredCompany(
                name=clean_company_name(c["name"]), domain=domain, website=c["website"],
                industry=c.get("subindustry") or c.get("industry"), location=c.get("all_locations"),
                country=_last_part(c.get("all_locations")), size_range=size_bucket(c.get("team_size")),
                description=c.get("one_liner"), source_url=c.get("url"), source_title=f"YC directory: {c['name']}",
                snippet=c.get("one_liner"), signals=signals,
                raw={k: c.get(k) for k in ("batch", "team_size", "isHiring", "stage", "tags", "regions")},
            ))
        return out


def _batch_year(batch: str | None) -> int:
    m = re.search(r"(\d{4})", batch or "")
    return int(m.group(1)) if m else 0


def _last_part(loc: str | None) -> str | None:
    if not loc:
        return None
    return loc.split(";")[0].split(",")[-1].strip() or None


# ============================================================================ HN hiring
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")


class HNHiringProvider(DiscoveryProvider):
    key = "hn_hiring"
    label = "Hacker News — Who is hiring?"
    kind = "hiring"
    description = "Companies posting in the monthly HN hiring thread (official HN Algolia API)."
    API = "https://hn.algolia.com/api/v1"

    def search(self, q: DiscoveryQuery, cfg: dict[str, Any]) -> list[DiscoveredCompany]:
        r = request_with_retry("GET", f"{self.API}/search_by_date",
                               params={"tags": "story,author_whoishiring", "hitsPerPage": 6}, retries=2)
        if r.status_code != 200:
            raise ProviderError(f"HN API returned HTTP {r.status_code}")
        thread = next((h for h in r.json().get("hits", []) if "who is hiring" in (h.get("title") or "").lower()), None)
        if not thread:
            return []
        thread_id = thread["objectID"]
        published = datetime.fromtimestamp(thread.get("created_at_i", time.time()), UTC)
        terms = [t.lower() for t in q.industries + q.keywords + ([q.text] if q.text else []) if t]
        geos = [g.lower() for g in q.geographies]
        out: list[DiscoveredCompany] = []
        seen: set[str] = set()
        page, skipped = 0, 0
        while len(out) < q.limit and page < 10:
            cr = request_with_retry("GET", f"{self.API}/search",
                                    params={"tags": f"comment,story_{thread_id}", "hitsPerPage": 100, "page": page},
                                    retries=2)
            hits = cr.json().get("hits", []) if cr.status_code == 200 else []
            if not hits:
                break
            for h in hits:
                if h.get("parent_id") != int(thread_id):
                    continue  # top-level posts only
                text = html.unescape(re.sub(r"<[^>]+>", " ", h.get("comment_text") or ""))
                first = text.strip().split("\n")[0][:300]
                low = text.lower()
                if terms and not any(t in low for t in terms):
                    continue
                if geos and not any(g in low for g in geos) and "remote" not in low:
                    continue
                parts = [p.strip() for p in first.split("|")]
                name = clean_company_name(re.sub(r"\(.*?\)", "", parts[0]).strip()) if parts else ""
                urls = _URL_RE.findall(h.get("comment_text") and html.unescape(h["comment_text"]) or "")
                domain, website = None, None
                for u in urls:
                    d = normalize_domain(u)
                    if d and d not in _HOSTED_JOB_DOMAINS:
                        domain, website = d, f"https://{d}"
                        break
                if not name or not domain or len(name) > 80 or domain in seen:
                    continue
                seen.add(domain)
                if skipped < q.offset:
                    skipped += 1
                    continue
                src = f"https://news.ycombinator.com/item?id={h['objectID']}"
                out.append(DiscoveredCompany(
                    name=name, domain=domain, website=website, location=parts[1] if len(parts) > 1 else None,
                    source_url=src, source_title=f"HN Who is hiring: {name}", snippet=first,
                    signals=[DiscoveredSignal("hiring", f"{name} posted roles in HN '{thread.get('title')}': {first[:200]}",
                                              src, published, first[:300], 0.8)],
                    raw={"thread": thread.get("title")},
                ))
                if len(out) >= q.limit:
                    break
            page += 1
        return out


_HOSTED_JOB_DOMAINS = {
    "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "ycombinator.com", "workatastartup.com",
    "bamboohr.com", "notion.site", "google.com", "linkedin.com", "smartrecruiters.com", "recruitee.com",
    "breezy.hr", "jobvite.com", "teamtailor.com", "github.com", "docs.google.com", "forms.gle",
    "calendly.com", "grnh.se", "jobs.lever.co", "wellfound.com", "angel.co", "apply.workable.com", "rippling.com", "gem.com",
}


# ============================================================================ RSS
NEWS_DOMAINS = {
    "techcrunch.com", "venturebeat.com", "businesswire.com", "prnewswire.com", "globenewswire.com",
    "reuters.com", "bloomberg.com", "forbes.com", "news.google.com", "medium.com", "substack.com",
    "eu-startups.com", "sifted.eu", "tech.eu", "finsmes.com", "crunchbase.com", "news.crunchbase.com",
    "uktech.news", "geekwire.com", "siliconangle.com", "theverge.com", "wired.com", "fortune.com",
    "inc.com", "fastcompany.com", "axios.com", "businessinsider.com", "cnbc.com", "ft.com",
}

_SIGNAL_PATTERNS = [
    ("funding", re.compile(r"\b(raises?|raised|secures?|closes?|lands?)\b.*\b(seed|series [a-f]|funding|round|\$|€|£)", re.I)),
    ("funding", re.compile(r"\b(seed|series [a-f]) (round|funding)\b", re.I)),
    ("acquisition", re.compile(r"\b(acquires?|acquired|acquisition of|merges? with)\b", re.I)),
    ("product_launch", re.compile(r"\b(launch(es|ed)?|unveils?|introduces?|debuts?)\b", re.I)),
    ("expansion", re.compile(r"\b(expands?|expansion|opens? (new )?(office|hq)|enters?)\b", re.I)),
    ("hiring", re.compile(r"\b(hiring|hires|appoints?|names?)\b.*\b(chief|head|vp|cto|cmo|ceo|coo|director)\b", re.I)),
    ("executive_appointment", re.compile(r"\b(appoints?|appointed|names?|named)\b.*\b(ceo|cto|cmo|coo|cio|chief)\b", re.I)),
    ("rebrand", re.compile(r"\b(rebrand(s|ed|ing)?|new brand identity)\b", re.I)),
]


def classify_signal_text(text: str) -> str | None:
    for kind, rx in _SIGNAL_PATTERNS:
        if rx.search(text or ""):
            return kind
    return None


class RSSProvider(DiscoveryProvider):
    key = "rss"
    label = "RSS / Atom feeds"
    kind = "rss"
    description = "Funding, hiring and launch announcements from feeds you configure on the campaign."

    def search(self, q: DiscoveryQuery, cfg: dict[str, Any]) -> list[DiscoveredCompany]:
        feeds: list[str] = q.params.get("rss_feeds") or []
        if not feeds:
            raise ProviderError("No RSS feeds configured on this campaign")
        terms = [t.lower() for t in q.industries + q.keywords if t]
        out: list[DiscoveredCompany] = []
        seen: set[str] = set()
        with client(timeout=20) as http:
            for feed_url in feeds[:20]:
                try:
                    r = http.get(feed_url)
                except Exception as e:  # noqa: BLE001
                    log.warning("rss fetch failed %s: %s", feed_url, e)
                    continue
                if r.status_code != 200:
                    continue
                parsed = feedparser.parse(r.content)
                for e in parsed.entries[:100]:
                    title = html.unescape(e.get("title", ""))
                    summary = html.unescape(re.sub(r"<[^>]+>", " ", e.get("summary", "")))[:500]
                    text = f"{title} {summary}"
                    if terms and not any(t in text.lower() for t in terms):
                        continue
                    link = e.get("link")
                    domain = normalize_domain(link)
                    published = _entry_date(e)
                    if not domain or domain in NEWS_DOMAINS or domain == normalize_domain(feed_url) or domain in seen:
                        continue  # item links to a news site: needs AI extraction (see discovery agent)
                    seen.add(domain)
                    kind = classify_signal_text(text)
                    signals = [DiscoveredSignal(kind, title[:300], link, published, summary[:300], 0.6)] if kind else []
                    out.append(DiscoveredCompany(
                        name=company_name_from_title(title, domain), domain=domain, website=f"https://{domain}",
                        source_url=link, source_title=title[:300], snippet=summary, signals=signals,
                        raw={"feed": feed_url},
                    ))
                    if len(out) >= q.limit:
                        return out
        return out


def _entry_date(e: Any) -> datetime | None:
    for k in ("published_parsed", "updated_parsed"):
        t = e.get(k)
        if t:
            try:
                return datetime(*t[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                pass
    return None


def news_rss_items(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Public Google News RSS search — used for business-signal research (not company discovery)."""
    s = get_settings()
    url = "https://news.google.com/rss/search"
    r = request_with_retry("GET", url, params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}, retries=2,
                           headers={"User-Agent": s.user_agent})
    if r.status_code != 200:
        raise ProviderError(f"News RSS returned HTTP {r.status_code}")
    parsed = feedparser.parse(r.content)
    items = []
    for e in parsed.entries[:limit]:
        src = e.get("source", {}) or {}
        items.append({
            "title": html.unescape(e.get("title", "")),
            "link": e.get("link"),
            "published_at": _entry_date(e),
            "source_name": src.get("title") if isinstance(src, dict) else None,
            "source_href": src.get("href") if isinstance(src, dict) else None,
            "summary": html.unescape(re.sub(r"<[^>]+>", " ", e.get("summary", "")))[:500],
        })
    return items
