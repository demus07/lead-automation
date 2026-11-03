"""Deterministic normalisation helpers used for deduplication."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

import tldextract

# Offline extractor: uses the bundled public-suffix snapshot, never fetches at runtime.
_extract = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True)

_COMPANY_SUFFIXES = re.compile(
    r"[,\s]+(inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|limited|plc|gmbh|ag|sa|s\.a\.|sas|bv|b\.v\.|pty|pty ltd|"
    r"co|co\.|corp|corp\.|corporation|company|srl|s\.r\.l\.|oy|ab|as|aps|kg|llp|pte|pte\. ltd\.)$",
    re.I,
)
_TITLE_SPLIT = re.compile(r"\s+[|\-–—:·•]\s+")
_GENERIC_TITLE_PARTS = {"home", "homepage", "welcome", "official site", "official website", "index"}


def normalize_domain(value: str | None) -> str | None:
    """'https://WWW.Acme.co.uk/about?x' → 'acme.co.uk'. Returns None if not a plausible domain."""
    if not value:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if "@" in v and "://" not in v:
        v = v.split("@", 1)[1]
    if "://" not in v:
        v = "http://" + v
    try:
        host = urlparse(v).hostname or ""
    except ValueError:
        return None
    host = host.strip(".")
    if not host or " " in host:
        return None
    if re.fullmatch(r"[\d.]+", host) or host == "localhost":
        return None
    ext = _extract(host)
    if not ext.domain or not ext.suffix:
        return None
    return f"{ext.domain}.{ext.suffix}"


def website_from_domain(domain: str) -> str:
    return f"https://{domain}"


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    if "://" not in u:
        u = "https://" + u
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    return u


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    e = email.strip().lower()
    if e.startswith("mailto:"):
        e = e[7:]
    e = e.split("?")[0]
    if not re.fullmatch(r"[a-z0-9._%+'-]+@[a-z0-9.-]+\.[a-z]{2,}", e):
        return None
    return e


def clean_company_name(name: str | None) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKC", name).strip()
    n = re.sub(r"\s+", " ", n)
    return n[:300]


def name_key(name: str | None) -> str:
    """Loose key for fuzzy duplicate detection when no domain is known."""
    n = clean_company_name(name).lower()
    n = _COMPANY_SUFFIXES.sub("", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def company_name_from_title(title: str | None, domain: str | None = None) -> str:
    """Derive a company name from an HTML title such as 'Acme — Payments for builders'."""
    if title:
        parts = [p.strip() for p in _TITLE_SPLIT.split(title) if p.strip()]
        parts = [p for p in parts if p.lower() not in _GENERIC_TITLE_PARTS]
        if domain:
            stem = domain.split(".")[0].replace("-", "").lower()
            for p in parts:
                if stem and stem in re.sub(r"[^a-z0-9]", "", p.lower()):
                    return clean_company_name(p)
        if parts:
            shortest = min(parts[:2], key=len)
            if len(shortest) <= 60:
                return clean_company_name(shortest)
    if domain:
        return domain.split(".")[0].replace("-", " ").title()
    return ""


def split_name(full_name: str) -> tuple[str | None, str | None]:
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])
