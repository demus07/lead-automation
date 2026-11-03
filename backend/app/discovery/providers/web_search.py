"""Optional web-search providers (API key or self-hosted). All map to a common result shape and a
deterministic "is this a company homepage?" filter. Results pointing at news/directories are kept as
evidence only (the Discovery Agent may extract companies from them when an LLM is configured).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.http import request_with_retry
from app.discovery.normalize import company_name_from_title, normalize_domain
from app.discovery.providers.base import (
    DiscoveredCompany,
    DiscoveredSignal,
    DiscoveryProvider,
    DiscoveryQuery,
    ProviderError,
    ProviderNotConfigured,
)
from app.discovery.providers.public_sources import NEWS_DOMAINS, classify_signal_text


class WebResult(dict):
    """{title, url, snippet, published}"""


def results_to_companies(results: list[WebResult], cfg: dict[str, Any], limit: int) -> tuple[list[DiscoveredCompany], list[WebResult]]:
    excluded = set(cfg.get("excluded_domains", [])) | NEWS_DOMAINS
    companies: list[DiscoveredCompany] = []
    leftovers: list[WebResult] = []
    seen: set[str] = set()
    for r in results:
        url = r.get("url") or ""
        domain = normalize_domain(url)
        if not domain:
            continue
        path = urlparse(url).path.strip("/")
        is_homepageish = path.count("/") <= 1 and not any(
            seg in path for seg in ("blog", "news", "article", "press", "202", "201", "jobs/", "careers/"))
        if domain in excluded or not is_homepageish:
            leftovers.append(r)
            continue
        if domain in seen:
            continue
        seen.add(domain)
        text = f"{r.get('title', '')} {r.get('snippet', '')}"
        kind = classify_signal_text(text)
        signals = [DiscoveredSignal(kind, r.get("title", "")[:300], url, None, r.get("snippet"), 0.4)] if kind else []
        companies.append(DiscoveredCompany(
            name=company_name_from_title(r.get("title"), domain), domain=domain, website=f"https://{domain}",
            source_url=url, source_title=r.get("title"), snippet=r.get("snippet"), signals=signals,
            description=r.get("snippet"),
        ))
        if len(companies) >= limit:
            break
    return companies, leftovers


class _WebSearchBase(DiscoveryProvider):
    kind = "web_search"
    requires_auth = True
    counts_against_search_quota = True
    cfg_key = ""

    def is_configured(self, cfg: dict[str, Any]) -> bool:
        return bool(cfg.get(self.cfg_key))

    def raw_search(self, text: str, cfg: dict[str, Any], count: int, offset: int = 0) -> list[WebResult]:
        raise NotImplementedError

    def search(self, q: DiscoveryQuery, cfg: dict[str, Any]) -> list[DiscoveredCompany]:
        if not self.is_configured(cfg):
            raise ProviderNotConfigured(f"{self.label} is not configured")
        if not q.text:
            raise ProviderError("Web search requires query text")
        results = self.raw_search(q.text, cfg, count=min(20, max(q.limit * 2, 10)), offset=q.offset)
        companies, leftovers = results_to_companies(results, cfg, q.limit)
        for c in companies:
            c.raw["query"] = q.text
        # stash non-company results for optional AI extraction by the engine
        if companies or leftovers:
            q.params.setdefault("_leftovers", []).extend(leftovers)
        return companies


class BraveSearchProvider(_WebSearchBase):
    key = "brave"
    label = "Brave Search API"
    cfg_key = "brave_api_key"
    description = "Independent web index. Free tier available. Requires API key."

    def raw_search(self, text, cfg, count, offset=0):
        r = request_with_retry("GET", "https://api.search.brave.com/res/v1/web/search",
                               params={"q": text, "count": min(count, 20), "offset": min(offset // max(count, 1), 9)},
                               headers={"X-Subscription-Token": cfg[self.cfg_key], "Accept": "application/json"})
        if r.status_code == 401 or r.status_code == 403:
            raise ProviderError("Brave Search rejected the API key")
        if r.status_code != 200:
            raise ProviderError(f"Brave Search HTTP {r.status_code}")
        return [WebResult(title=w.get("title", ""), url=w.get("url", ""), snippet=w.get("description", ""),
                          published=w.get("page_age")) for w in r.json().get("web", {}).get("results", [])]


class TavilyProvider(_WebSearchBase):
    key = "tavily"
    label = "Tavily Search API"
    cfg_key = "tavily_api_key"
    description = "Search API designed for AI agents. Requires API key."

    def raw_search(self, text, cfg, count, offset=0):
        r = request_with_retry("POST", "https://api.tavily.com/search",
                               json={"query": text, "max_results": min(count, 20), "search_depth": "basic"},
                               headers={"Authorization": f"Bearer {cfg[self.cfg_key]}"})
        if r.status_code in (401, 403):
            raise ProviderError("Tavily rejected the API key")
        if r.status_code != 200:
            raise ProviderError(f"Tavily HTTP {r.status_code}")
        return [WebResult(title=w.get("title", ""), url=w.get("url", ""), snippet=(w.get("content") or "")[:400],
                          published=w.get("published_date")) for w in r.json().get("results", [])]


class SerpAPIProvider(_WebSearchBase):
    key = "serpapi"
    label = "SerpAPI (Google results)"
    cfg_key = "serpapi_api_key"
    description = "Google search results via SerpAPI. Requires API key."

    def raw_search(self, text, cfg, count, offset=0):
        r = request_with_retry("GET", "https://serpapi.com/search.json",
                               params={"q": text, "num": min(count, 20), "start": offset, "engine": "google",
                                       "api_key": cfg[self.cfg_key]})
        if r.status_code in (401, 403):
            raise ProviderError("SerpAPI rejected the API key")
        if r.status_code != 200:
            raise ProviderError(f"SerpAPI HTTP {r.status_code}")
        return [WebResult(title=w.get("title", ""), url=w.get("link", ""), snippet=w.get("snippet", ""),
                          published=w.get("date")) for w in r.json().get("organic_results", [])]


class SearXNGProvider(_WebSearchBase):
    key = "searxng"
    label = "SearXNG (self-hosted, open source)"
    cfg_key = "searxng_url"
    requires_auth = False
    description = "Self-hosted open-source metasearch. Point to your instance URL (JSON format enabled)."

    def raw_search(self, text, cfg, count, offset=0):
        base = cfg[self.cfg_key].rstrip("/")
        r = request_with_retry("GET", f"{base}/search",
                               params={"q": text, "format": "json", "pageno": 1 + offset // max(count, 1)})
        if r.status_code != 200:
            raise ProviderError(f"SearXNG HTTP {r.status_code} (is JSON output enabled?)")
        return [WebResult(title=w.get("title", ""), url=w.get("url", ""), snippet=w.get("content", ""),
                          published=w.get("publishedDate")) for w in r.json().get("results", [])][:count]
