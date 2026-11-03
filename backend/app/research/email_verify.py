"""Email checks.

* Syntax + DNS MX lookup → ``domain_valid`` (the domain accepts mail; the mailbox is NOT verified).
* Optional Hunter.io verifier → ``verified`` only when the provider reports the mailbox deliverable.
* We never SMTP-probe mailboxes ourselves and never mark a guessed address verified.
"""
from __future__ import annotations

import logging

import dns.exception
import dns.resolver
from sqlalchemy.orm import Session

from app.core.http import request_with_retry
from app.discovery.normalize import normalize_email
from app.models import Contact, EmailStatus
from app.models.base import utcnow
from app.services import settings_service

log = logging.getLogger(__name__)


def mx_records(domain: str) -> list[str]:
    try:
        ans = dns.resolver.resolve(domain, "MX", lifetime=5)
        return sorted(str(r.exchange).rstrip(".") for r in ans)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        return []


def check_email(db: Session, email: str) -> tuple[EmailStatus | None, dict]:
    e = normalize_email(email)
    if not e:
        return EmailStatus.INVALID, {"reason": "syntax"}
    cfg = settings_service.get_section(db, "enrichment")
    detail: dict = {}
    if cfg.get("verification_provider") == "hunter" and cfg.get("hunter_api_key"):
        r = request_with_retry("GET", "https://api.hunter.io/v2/email-verifier",
                               params={"email": e, "api_key": cfg["hunter_api_key"]}, retries=1, timeout=30)
        if r.status_code == 200:
            data = r.json().get("data", {})
            detail = {"provider": "hunter", "result": data.get("result"), "status": data.get("status"),
                      "score": data.get("score")}
            if data.get("status") == "valid" or data.get("result") == "deliverable":
                return EmailStatus.VERIFIED, detail
            if data.get("status") == "invalid" or data.get("result") == "undeliverable":
                return EmailStatus.INVALID, detail
            # accept_all / unknown / webmail → fall through to MX check, not verified
        else:
            detail = {"provider": "hunter", "error": f"HTTP {r.status_code}"}
    if cfg.get("allow_mx_check", True):
        mx = mx_records(e.split("@")[1])
        detail["mx"] = mx[:5]
        return (EmailStatus.DOMAIN_VALID if mx else EmailStatus.INVALID), detail
    return None, detail


def check_contact_email(db: Session, contact: Contact) -> None:
    status, detail = check_email(db, contact.email or "")
    contact.email_checked_at = utcnow()
    contact.email_check_detail = detail
    if status is None:
        return
    if status == EmailStatus.VERIFIED:
        contact.email_status = EmailStatus.VERIFIED  # provider-confirmed only
    elif status == EmailStatus.INVALID:
        contact.email_status = EmailStatus.INVALID
    elif contact.email_status in (EmailStatus.UNVERIFIED, EmailStatus.NONE):
        contact.email_status = status  # domain_valid; keep "published" if it was found on the official site
