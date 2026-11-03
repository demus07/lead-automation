"""Shared HTTP client helpers with retries for transient failures."""
from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


class TransientHTTPError(Exception):
    """Raised after retries are exhausted on a transient error (caller may retry later)."""


def client(timeout: float = 20.0, **kw: Any) -> httpx.Client:
    headers = {"User-Agent": get_settings().user_agent, "Accept-Language": "en;q=0.9,*;q=0.5"}
    headers.update(kw.pop("headers", {}) or {})
    return httpx.Client(timeout=timeout, headers=headers, follow_redirects=kw.pop("follow_redirects", True), **kw)


def request_with_retry(
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.0,
    timeout: float = 20.0,
    http: httpx.Client | None = None,
    **kw: Any,
) -> httpx.Response:
    own = http is None
    http = http or client(timeout=timeout)
    try:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = http.request(method, url, **kw)
                if r.status_code in TRANSIENT_STATUS and attempt < retries:
                    wait = _retry_after(r) or backoff * (2**attempt) + random.random() * 0.25
                    log.info("transient %s from %s, retrying in %.1fs", r.status_code, url, wait)
                    time.sleep(min(wait, 30))
                    continue
                return r
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                last = e
                if attempt < retries:
                    time.sleep(backoff * (2**attempt) + random.random() * 0.25)
                    continue
        raise TransientHTTPError(f"{method} {url} failed after {retries + 1} attempts: {last}")
    finally:
        if own:
            http.close()


def _retry_after(r: httpx.Response) -> float | None:
    v = r.headers.get("retry-after")
    if v and v.isdigit():
        return float(v)
    return None
