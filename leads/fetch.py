"""Polite HTTP: identifies itself, respects robots.txt, caps page size."""
import os
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = f"LeadResearchBot/1.0 (+{os.getenv('CRAWLER_CONTACT', 'no contact set')})"
MAX_BYTES = 2_000_000
_robots: dict[str, RobotFileParser | None] = {}


def client(timeout: float = 15) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)


def allowed(http: httpx.Client, url: str) -> bool:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        try:
            r = http.get(base + "/robots.txt")
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots[base] = rp
        except httpx.HTTPError:
            _robots[base] = None  # unreachable robots.txt: treat as allowed
    rp = _robots[base]
    return rp is None or rp.can_fetch(USER_AGENT, url)


def get_page(http: httpx.Client, url: str) -> dict | None:
    """Fetch an HTML page. Returns {url, final_url, html, ms, bytes} or None."""
    if not allowed(http, url):
        return None
    start = time.monotonic()
    try:
        r = http.get(url)
    except httpx.HTTPError:
        return None
    ms = round((time.monotonic() - start) * 1000)
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return None
    content = r.content[:MAX_BYTES]
    return {"url": url, "final_url": str(r.url), "html": content.decode(r.encoding or "utf-8", "replace"),
            "ms": ms, "bytes": len(r.content)}


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host if "." in host else None
