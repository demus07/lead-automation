"""find → research → contacts → draft → (you approve) → send. Plus a background scheduler."""
import threading
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from . import contacts, db, discover, draft, inbox, research, send

state = {"running": False, "log": []}
_lock = threading.Lock()


def log(msg: str) -> None:
    state["log"] = [f"{datetime.now():%H:%M:%S}  {msg}", *state["log"]][:50]


def process(lead_id: int) -> None:
    """Research one lead and, if it's a fit and reachable, queue a draft for approval."""
    lead = db.get_lead(lead_id)
    s = db.settings()
    pages = research.crawl(lead["website"])
    if not pages:
        db.update_lead(lead_id, status="error", note="Site unreachable or blocked by robots.txt")
        return
    if not research.readable(pages):
        db.update_lead(lead_id, status="skipped", note="Couldn't read the site (bot check or empty page)")
        return
    r = research.analyse(pages, lead["signals"])
    if s.get("service_focus") in ("website", "systems"):
        r["recommended"] = s["service_focus"]
    c = contacts.find(pages, lead["domain"], lead.get("email"))
    db.update_lead(lead_id, research=r, contacts=c, status="researched", note=None)

    score = r["scores"][r["recommended"]]
    if score < int(s["min_score"] or 0):
        db.update_lead(lead_id, status="skipped", note=f"Best score {score} is below the minimum {s['min_score']}")
        return
    if not draft.hooks(r):
        db.update_lead(lead_id, status="skipped", note="Nothing worth raising with them")
        return
    if c["best_email"] and not db.is_blocked(c["best_email"]) and not db.already_contacted(c["best_email"]):
        channel, recipient = "email", c["best_email"]
    elif c["best_dm"]:
        channel, recipient = "dm", c["best_dm"]
    else:
        # A good fit is still worth having: it stays in the list for you to find a contact by hand.
        db.update_lead(lead_id, status="needs_contact", note="Good fit, but no email or profile on their site")
        return
    msg = draft.write(lead, r, c, channel, s)
    if draft.last_error["text"]:
        log(draft.last_error["text"])
    db.add_message(lead_id, channel, recipient, msg["subject"], msg["body"], drafted_by=msg["drafted_by"])
    db.update_lead(lead_id, status="drafted")


def queue_follow_ups() -> int:
    """Draft one follow-up for anyone who hasn't answered. These wait for approval like everything else."""
    s, n = db.settings(), 0
    for lead in db.follow_ups_to_draft():
        first = next((m for m in db.messages_for(lead["id"]) if m["kind"] == "first" and m["status"] == "sent"), None)
        if first and first["channel"] == "email" and not db.is_blocked(first["recipient"]):
            msg = draft.write_follow_up(lead, first, s)
            db.add_message(lead["id"], "email", first["recipient"], msg["subject"], msg["body"], kind="follow_up",
                           drafted_by=msg["drafted_by"])
            n += 1
    return n


def run(discover_new: bool = True) -> None:
    if not _lock.acquire(blocking=False):
        return
    state["running"] = True
    try:
        s = db.settings()
        try:
            for event in inbox.check():  # first, so nobody who replied gets a follow-up
                log(event)
        except Exception as e:  # a mail hiccup shouldn't stop lead finding
            log(f"Couldn't read the inbox: {e}")
        if discover_new:
            ids = discover.discover(int(s["leads_per_run"] or 10))
            log(f"Found {len(ids)} new leads")
        for lead in db.list_leads("new"):
            try:
                process(lead["id"])
                log(f"{lead['name']}: {db.get_lead(lead['id'])['status']}")
            except Exception as e:  # one bad site shouldn't stop the run
                traceback.print_exc()
                db.update_lead(lead["id"], status="error", note=str(e)[:300])
                log(f"{lead['name']}: error — {e}")
        if n := queue_follow_ups():
            log(f"Drafted {n} follow-up(s)")
    except Exception as e:
        traceback.print_exc()
        log(f"Run failed: {e}")
    finally:
        state["running"] = False
        db.save_settings({"last_run": db.now()})
        _lock.release()


def run_in_background(discover_new: bool = True) -> None:
    threading.Thread(target=run, args=(discover_new,), daemon=True).start()


def scheduler() -> None:
    """Checks every minute whether an automatic run is due."""
    while True:
        s = db.settings()
        if s["auto_run"] == "on" and not state["running"]:
            due = timedelta(hours=float(s["interval_hours"] or 24))
            last = datetime.fromisoformat(s["last_run"]) if s["last_run"] else None
            if last is None or datetime.now(timezone.utc) - last >= due:
                run()
        time.sleep(60)


def approve(msg_id: int, subject: str, body: str) -> str | None:
    """Send (email) or mark as sent (DM, which you send yourself). Returns an error message or None."""
    m = db.get_message(msg_id)
    if not m or m["status"] != "pending":
        return "That message is no longer pending."
    if db.is_blocked(m["recipient"]):
        return f"{m['recipient']} is on the do-not-contact list."
    if m["kind"] == "first" and db.already_contacted(m["recipient"]):
        return f"{m['recipient']} has already been contacted."
    db.update_message(msg_id, subject=subject, body=body)
    message_id, first = None, None
    if m["channel"] == "email":
        if not send.configured():
            return "Email isn't set up yet — add SMTP_* to .env."
        if db.sent_today() >= int(db.settings()["daily_send_limit"] or 20):
            return "Daily send limit reached. It resets tomorrow (UTC)."
        if m["kind"] == "follow_up":
            first = next((x for x in db.messages_for(m["lead_id"]) if x["kind"] == "first" and x["status"] == "sent"), None)
        try:
            message_id = send.send_email(m["recipient"], subject, body, first["message_id"] if first else None)
        except Exception as e:
            db.update_message(msg_id, status="failed", error=str(e)[:300])
            return f"Sending failed: {e}"
    db.update_message(msg_id, status="sent", sent_at=db.now(), error=None, message_id=message_id)
    days = int(db.settings()["follow_up_days"] or 4)
    # One follow-up only: after that, leave them alone.
    next_up = None if m["kind"] == "follow_up" else (date.today() + timedelta(days=days)).isoformat()
    db.update_lead(m["lead_id"], status="contacted", follow_up=next_up)
    db.add_note(m["lead_id"], f"Sent {m['channel']} to {m['recipient']}: “{subject or body[:60]}”")
    return None


def reject(msg_id: int) -> None:
    m = db.get_message(msg_id)
    db.update_message(msg_id, status="rejected")
    if m["kind"] == "first":
        db.update_lead(m["lead_id"], status="skipped", note="Draft rejected")
    else:
        db.update_lead(m["lead_id"], follow_up=None)


def redraft(lead_id: int) -> None:
    lead = db.get_lead(lead_id)
    messages = db.messages_for(lead_id)
    old = next((m for m in messages if m["status"] == "pending"), None)
    if not old or not lead["research"]:
        return
    s = db.settings()
    if old["kind"] == "follow_up":
        first = next(m for m in messages if m["kind"] == "first" and m["status"] == "sent")
        msg = draft.write_follow_up(lead, first, s)
    else:
        msg = draft.write(lead, lead["research"], lead["contacts"], old["channel"], s)
    db.update_message(old["id"], subject=msg["subject"], body=msg["body"], drafted_by=msg["drafted_by"])
