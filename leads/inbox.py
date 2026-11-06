"""Reading your inbox over IMAP (the same Gmail App Password works) so replies, opt-outs and bounces
update the CRM by themselves. Read-only: mail is never marked as read, moved or deleted."""
import email
import imaplib
import os
import re
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr

from . import db

OPT_OUT = re.compile(r"\b(unsubscribe|remove me|take me off|stop (emailing|contacting)|do not (email|contact)|"
                     r"don'?t (email|contact)|no thanks|not interested)\b", re.I)
AUTO = re.compile(r"\b(out of (the )?office|automatic reply|auto[- ]?reply|autoresponder|away from)\b", re.I)
BOUNCE_FROM = re.compile(r"(mailer-daemon|postmaster)@", re.I)


def configured() -> bool:
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def connect() -> imaplib.IMAP4_SSL:
    host = os.getenv("IMAP_HOST") or os.getenv("SMTP_HOST", "").replace("smtp.", "imap.")
    box = imaplib.IMAP4_SSL(host, timeout=30)
    box.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
    return box


def _text(msg) -> str:
    part = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None)
    if not part:
        return ""
    return (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")


def _new_reply_only(text: str) -> str:
    """Drop the quoted original, so our own opt-out line in the quote isn't read as their answer."""
    lines = []
    for ln in text.splitlines():
        if ln.startswith(">") or re.match(r"On .+ wrote:\s*$", ln):
            break
        lines.append(ln)
    return "\n".join(lines).strip()


def _match(sender: str, sent: list[dict]) -> dict | None:
    domain = sender.split("@")[-1]
    return next((m for m in sent if m["recipient"] == sender), None) or \
        next((m for m in sent if m["lead_domain"] == domain or m["recipient"].split("@")[-1] == domain and
              domain not in ("gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com")), None)


def _handle(msg, sent: list[dict]) -> str | None:
    sender = parseaddr(msg.get("From", ""))[1].lower()
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    body = _text(msg)
    if BOUNCE_FROM.search(sender):
        hit = next((m for m in sent if m["recipient"] in body.lower()), None)
        if hit:
            db.update_message(hit["id"], status="bounced", error="Address bounced")
            db.update_lead(hit["lead_id"], status="error", note="Email bounced", follow_up=None)
            db.block(hit["recipient"])
            return f"Bounced: {hit['recipient']}"
        return None
    hit = _match(sender, sent)
    if not hit:
        return None
    if msg.get("Auto-Submitted", "no").lower() != "no" or AUTO.search(subject):
        return None  # an out-of-office isn't a reply; leave the follow-up in place
    reply = _new_reply_only(body)
    db.reject_pending(hit["lead_id"])
    if OPT_OUT.search(reply):
        db.block(sender)
        db.update_lead(hit["lead_id"], status="lost", note="Opted out by reply", follow_up=None)
        db.add_note(hit["lead_id"], f"Opted out by reply: “{reply[:200]}”")
        return f"Opt-out: {sender}"
    db.update_lead(hit["lead_id"], status="replied", follow_up=date.today().isoformat())
    db.add_note(hit["lead_id"], f"Reply from {sender}: “{reply[:500]}”")
    return f"Reply: {sender}"


def check() -> list[str]:
    """Scan recent mail. Returns one line per event handled."""
    sent = db.sent_emails()
    if not sent or not configured():
        return []
    events = []
    box = connect()
    try:
        box.select("INBOX", readonly=True)
        since = (date.today() - timedelta(days=30)).strftime("%d-%b-%Y")
        ids = box.search(None, "SINCE", since)[1][0].split()
        for mid in ids[-300:]:
            head = email.message_from_bytes(box.fetch(mid, "(BODY.PEEK[HEADER])")[1][0][1])
            key = head.get("Message-ID") or f"{head.get('From')}|{head.get('Date')}"
            if db.mail_seen(key):
                continue
            db.mark_mail_seen(key)
            msg = email.message_from_bytes(box.fetch(mid, "(BODY.PEEK[])")[1][0][1])
            if event := _handle(msg, sent):
                events.append(event)
                sent = db.sent_emails()  # a lead that just replied isn't awaiting a response any more
    finally:
        box.logout()
    return events
