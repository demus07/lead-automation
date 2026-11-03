"""Polite, robots-aware page fetching with caching.

* robots.txt is fetched once per host (cached 24h) and checked for our User-Agent before every URL.
* Crawl-delay is honoured (or the configured minimum delay), per host.
* Only HTML is fetched; bodies are capped at 2 MB; no authentication, cookies, CAPTCHA solving or
  paywall bypass is attempted — 401/403/429 responses are recorded as blocked.
* Pages are cached in ``page_cache`` and re-used until ``recrawl_after_days``.
* Playwright (optional) renders JavaScript-heavy pages when static HTML has too little text.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import urllib.robotparser
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.discovery.normalize import normalize_domain
from app.models import PageCache
from app.models.base import utcnow

log = logging.getLogger(__name__)
MAX_BYTES = 2 * 1024 * 1024
_ROBOTS: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None, float | None, str]] = {}
_LAST_HIT: dict[str, float] = {}
_LOCK = threading.Lock()


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status_code: int | None = None
    html: str | None = None
    content_type: str | None = None
    from_cache: bool = False
    rendered: bool = False
    blocked_reason: str | None = None
    elapsed_ms: int | None = None
    headers: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.html is not None and self.blocked_reason is None and (self.status_code or 0) < 400


def _robots_for(origin: str, http: httpx.Client) -> tuple[urllib.robotparser.RobotFileParser | None, float | None, str]:
    now = time.time()
    with _LOCK:
        cached = _ROBOTS.get(origin)
        if cached and now - cached[0] < 86400:
            return cached[1], cached[2], cached[3]
    rp = urllib.robotparser.RobotFileParser()
    status = "missing"
    try:
        r = http.get(f"{origin}/robots.txt", timeout=10)
        if r.status_code == 200:
            rp.parse(r.text.splitlines())
            status = "ok"
        elif r.status_code in (401, 403):
            rp.disallow_all = True  # per RFC 9309: access restricted → treat as disallow
            status = f"restricted({r.status_code})"
        else:
            rp.allow_all = True
            status = f"none({r.status_code})"
    except httpx.HTTPError:
        rp.allow_all = True
        status = "unreachable"
    ua = get_settings().user_agent
    delay = rp.crawl_delay(ua) or rp.crawl_delay("*")
    with _LOCK:
        _ROBOTS[origin] = (now, rp, float(delay) if delay else None, status)
    return rp, float(delay) if delay else None, status


def robots_info(url: str, http: httpx.Client) -> dict:
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    rp, delay, status = _robots_for(origin, http)
    return {"origin": origin, "status": status, "crawl_delay": delay,
            "homepage_allowed": bool(rp.can_fetch(get_settings().user_agent, origin + "/")) if rp else True}


def _polite_wait(host: str, delay: float) -> None:
    with _LOCK:
        last = _LAST_HIT.get(host, 0.0)
        wait = last + delay - time.time()
        _LAST_HIT[host] = max(time.time(), last + delay)
    if wait > 0:
        time.sleep(min(wait, 30))


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def fetch(db: Session | None, url: str, *, http: httpx.Client, min_delay: float = 1.5,
          max_age_days: int = 14, allow_render: bool = True) -> FetchResult:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return FetchResult(url=url, blocked_reason="invalid_url")
    if _is_private_host(p.hostname):
        return FetchResult(url=url, blocked_reason="private_address")

    if db is not None:
        cached = db.scalar(select(PageCache).where(PageCache.url_hash == url_hash(url)))
        if cached and cached.fetched_at > utcnow() - timedelta(days=max_age_days):
            return FetchResult(url=url, final_url=cached.final_url, status_code=cached.status_code, html=cached.html,
                               content_type=cached.content_type, from_cache=True, rendered=cached.rendered,
                               blocked_reason=cached.blocked_reason, headers=cached.headers or {})

    ua = get_settings().user_agent
    rp, crawl_delay, _ = _robots_for(f"{p.scheme}://{p.netloc}", http)
    if rp is not None and not rp.can_fetch(ua, url):
        res = FetchResult(url=url, blocked_reason="robots_disallow")
        _store(db, res)
        return res
    _polite_wait(p.netloc, max(min_delay, crawl_delay or 0))
    t0 = time.perf_counter()
    try:
        with http.stream("GET", url, headers={"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"}) as r:
            ctype = r.headers.get("content-type", "")
            res = FetchResult(url=url, final_url=str(r.url), status_code=r.status_code, content_type=ctype,
                              headers={k: v for k, v in r.headers.items()
                                       if k.lower() in ("server", "x-powered-by", "content-language", "x-generator")})
            # Redirects off-site to a different registered domain are recorded but not followed further.
            if r.status_code in (401, 403):
                res.blocked_reason = f"access_restricted_{r.status_code}"
            elif r.status_code == 429:
                res.blocked_reason = "rate_limited"
            elif r.status_code >= 400:
                res.blocked_reason = f"http_{r.status_code}"
            elif "html" not in ctype.lower():
                res.blocked_reason = "not_html"
            else:
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                res.html = body[:MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
                if _looks_like_challenge(res.html):
                    res.blocked_reason = "bot_challenge"  # never attempt to solve CAPTCHAs/challenges
                    res.html = None
    except httpx.HTTPError as e:
        res = FetchResult(url=url, blocked_reason=f"network_error:{type(e).__name__}")
    res.elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if res.ok and allow_render and get_settings().playwright_enabled and _needs_render(res.html or ""):
        rendered = _render(url)
        if rendered:
            res.html, res.rendered = rendered, True
    _store(db, res)
    return res


def _store(db: Session | None, res: FetchResult) -> None:
    if db is None:
        return
    h = url_hash(res.url)
    row = db.scalar(select(PageCache).where(PageCache.url_hash == h))
    if row is None:
        row = PageCache(url_hash=h, url=res.url[:2000], fetched_at=utcnow())
        db.add(row)
    row.domain = normalize_domain(res.url)
    row.status_code, row.content_type, row.final_url = res.status_code, res.content_type, res.final_url
    row.html = res.html
    row.content_hash = hashlib.sha256((res.html or "").encode()).hexdigest() if res.html else None
    row.fetched_at = utcnow()
    row.rendered, row.blocked_reason, row.elapsed_ms, row.headers = res.rendered, res.blocked_reason, res.elapsed_ms, res.headers
    db.flush()


def _looks_like_challenge(html: str) -> bool:
    low = html[:5000].lower()
    return any(s in low for s in ("cf-challenge", "challenge-platform", "captcha", "are you a robot",
                                  "attention required! | cloudflare", "ddos protection by"))


def _needs_render(html: str) -> bool:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    return len(text) < 400 and bool(soup.find(id=("root", "__next", "app")) or soup.find("div", id="app"))


def _render(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.info("Playwright not installed; skipping render for %s", url)
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(user_agent=get_settings().user_agent)
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            browser.close()
            return html[:MAX_BYTES]
    except Exception as e:  # noqa: BLE001
        log.warning("render failed for %s: %s", url, e)
        return None


@lru_cache(maxsize=4096)
def _is_private_host(host: str) -> bool:
    """SSRF guard: never fetch internal addresses (cached per host)."""
    import ipaddress
    import socket

    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # resolution failure surfaces as a network error later
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def reset_caches() -> None:
    with _LOCK:
        _ROBOTS.clear()
        _LAST_HIT.clear()


def now_utc() -> datetime:
    return datetime.now(UTC)
