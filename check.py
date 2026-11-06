"""Checks every connection and says plainly what works. Sends nothing, and changes nothing.
Run: .venv/bin/python check.py"""
import os
import smtplib

import httpx
from dotenv import load_dotenv

load_dotenv()

from leads import db, discover, draft, inbox, render, send  # noqa: E402


def report(name, fn):
    try:
        print(f"ok    {name}: {fn()}")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  {name}: {e}")


def llm():
    if not draft.llm_configured():
        raise RuntimeError("LLM_BASE_URL / LLM_MODEL aren't set; drafts will use the template")
    r = httpx.get(os.getenv("LLM_BASE_URL").rstrip("/") + "/models", timeout=20,
                  headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY') or 'none'}"})
    if r.status_code == 200:
        ids = [m["id"] for m in r.json().get("data", [])]
        if ids and os.getenv("LLM_MODEL") not in ids:
            raise RuntimeError(f"{os.getenv('LLM_MODEL')} isn't available. Available: {', '.join(ids[:15])}")
    return draft.call_llm('Reply with JSON only: {"ok": true}', "ping")


def smtp():
    if not send.configured():
        raise RuntimeError("SMTP_* isn't set")
    with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
    return "login accepted"


def imap():
    box = inbox.connect()
    box.logout()
    return "login accepted"


def browser():
    out = render.render("https://example.com")
    if not out:
        raise RuntimeError("run: .venv/bin/python -m playwright install chromium")
    return "headless Chrome works"


def target():
    s = db.settings()
    if "osm" in db.csv_setting(s, "sources") and not (s["cities"] and s["categories"]):
        raise RuntimeError("osm is on, but Cities or Categories are empty in Settings")
    missing = [k for k in ("sender_name", "postal_address") if not s[k]]
    if missing:
        raise RuntimeError(f"still empty in Settings: {', '.join(missing)}")
    return s["target_description"] or "set"


db.init()
report("Target settings", target)
report("Browser", browser)
report("AI drafting", llm)
report("Sending (SMTP)", smtp)
report("Reading replies (IMAP)", imap)
