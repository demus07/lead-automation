"""Who to contact, and how: emails and social profiles published on the company's own site.

Only addresses found on their pages are used; we never guess addresses. An MX lookup confirms the
domain accepts mail (it does not prove the mailbox exists).
"""
import re
from urllib.parse import unquote

import dns.exception
import dns.resolver

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Addresses we'd rather not cold-email, in order of preference for the rest.
SKIP_LOCALS = {"noreply", "no-reply", "donotreply", "privacy", "legal", "abuse", "security", "billing", "jobs",
               "careers", "hr", "press", "media", "support", "help", "dpo", "gdpr", "unsubscribe"}
GOOD_GENERIC = ["founders", "founder", "hello", "hi", "contact", "team", "info", "sales", "partnerships"]
SOCIALS = {"linkedin": re.compile(r"linkedin\.com/(company|in)/[^/?#\s\"']+", re.I),
           "x": re.compile(r"(?:twitter|x)\.com/(?!intent|share|home)[A-Za-z0-9_]{2,15}(?=[/?#\"'\s]|$)", re.I),
           "instagram": re.compile(r"instagram\.com/(?!p/|reel/|explore)[A-Za-z0-9_.]{2,30}", re.I),
           "facebook": re.compile(r"facebook\.com/(?!sharer|share|plugins|tr|dialog|login)[A-Za-z0-9_.-]{3,60}", re.I)}
# Small businesses often use one of these as their real address; trust it only from a mailto: link.
FREE_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "hotmail.co.uk", "yahoo.com", "yahoo.co.uk",
             "icloud.com", "btinternet.com", "aol.com"}


def _cf_decode(hexstr: str) -> str:
    """Cloudflare 'email protection' obfuscates addresses as XOR'd hex; undo it."""
    key = int(hexstr[:2], 16)
    return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))


def emails_in(html: str, text: str, domain: str) -> set[str]:
    """Real links and visible text only: raw HTML is full of form placeholders and example addresses."""
    mailto = {unquote(m).lower() for m in re.findall(r"mailto:([^\"'?>\s]+)", html, re.I)}
    found = mailto | set(EMAIL_RE.findall(text))
    found |= {_cf_decode(h) for h in re.findall(r'data-cfemail="([0-9a-f]+)"', html, re.I)}
    out = set()
    for e in found:
        e = e.strip().strip(".").lower()
        if not EMAIL_RE.fullmatch(e) or re.search(r"\.(png|jpe?g|gif|svg|webp)$", e):
            continue
        # Keep addresses on their own domain (or a subdomain of it); skips Sentry DSNs, theme authors, etc.
        host = e.split("@")[1]
        if host == domain or host.endswith("." + domain) or (host in FREE_MAIL and e in mailto):
            out.add(e)
    return out


def rank(email: str) -> int:
    local = email.split("@")[0]
    if local in SKIP_LOCALS:
        return 99
    if local in GOOD_GENERIC:
        return 10 + GOOD_GENERIC.index(local)
    return 0  # a person's address (jane@, jane.doe@) beats any shared inbox


def first_name(email: str) -> str | None:
    local = email.split("@")[0]
    if rank(email) != 0:
        return None
    part = re.split(r"[._-]", local)[0]
    return part.title() if part.isalpha() and len(part) > 2 else None


def has_mx(domain: str) -> bool:
    try:
        return bool(dns.resolver.resolve(domain, "MX", lifetime=5))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        return False


def find(pages: list[dict], domain: str, known_email: str | None = None) -> dict:
    emails, socials = {}, {}
    if known_email and EMAIL_RE.fullmatch(known_email.strip()):
        emails[known_email.strip().lower()] = "OpenStreetMap listing"
    for p in pages:
        for e in emails_in(p["html"], p["text"], domain):
            emails.setdefault(e, p["url"])
        for name, rx in SOCIALS.items():
            for _, href in p["links"]:
                m = rx.search(href)
                if m and name not in socials:
                    socials[name] = "https://" + m.group(0).rstrip("/")
    usable = sorted((e for e in emails if rank(e) < 99), key=rank)
    best_email = next((e for e in usable if has_mx(e.split("@")[1])), None)
    # Prefer a person's LinkedIn over the company page for a DM.
    linkedin = socials.get("linkedin", "")
    dm = linkedin if "/in/" in linkedin else (socials.get("instagram") or socials.get("x") or linkedin
                                              or socials.get("facebook"))
    return {
        "emails": [{"email": e, "found_on": emails[e]} for e in sorted(emails, key=rank)],
        "socials": socials,
        "best_email": best_email,
        "first_name": first_name(best_email) if best_email else None,
        "best_dm": dm,
    }
