"""SQLite storage. Two tables that matter: leads and messages. Settings are key/value."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "leads.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL UNIQUE,
    website TEXT NOT NULL,
    description TEXT,
    location TEXT,
    source TEXT,
    source_url TEXT,
    email TEXT,                     -- address given by the source itself, if any
    signals TEXT DEFAULT '[]',      -- JSON list of strings from discovery (hiring, recent batch…)
    status TEXT DEFAULT 'new',      -- new → researched → drafted → contacted → replied → meeting → won | lost
                                    -- (or skipped / error)
    note TEXT,                      -- why it was skipped / what failed
    follow_up TEXT,                 -- YYYY-MM-DD, optional
    research TEXT,                  -- JSON: checks, problems, scores, recommendation
    contacts TEXT,                  -- JSON: emails, socials, best contact
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,          -- email | dm
    recipient TEXT NOT NULL,        -- email address or profile URL
    subject TEXT,
    body TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending → sent | rejected | failed | bounced
    kind TEXT DEFAULT 'first',      -- first | follow_up
    drafted_by TEXT,                -- model name, or 'template'
    message_id TEXT,                -- so a follow-up lands in the same email thread
    error TEXT,
    created_at TEXT,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS seen_mail (message_id TEXT PRIMARY KEY);  -- inbox mail already handled
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS do_not_contact (value TEXT PRIMARY KEY);  -- domains or email addresses
"""

# Columns added since the first version, for databases created before them.
MIGRATIONS = {"leads": {"email": "TEXT"},
              "messages": {"kind": "TEXT DEFAULT 'first'", "drafted_by": "TEXT", "message_id": "TEXT"}}

DEFAULT_SETTINGS = {
    "target_description": "",
    "service_focus": "any",
    "sources": "osm",
    "cities": "",
    "categories": "",
    "keywords": "",
    "locations": "",
    "min_team": "",
    "max_team": "",
    "leads_per_run": "10",
    "auto_run": "off",
    "interval_hours": "24",
    "daily_send_limit": "20",
    "min_score": "50",
    "sender_name": "",
    "studio_name": "ALRO",
    "studio_url": "https://alro.studio",
    "website_pitch": "We design and build bespoke websites and landing pages that translate a business's "
                     "identity into a clear, cohesive experience.",
    "systems_pitch": "We build Company Intelligence: one place where a team's knowledge from Slack, email and "
                     "docs becomes searchable, with commitments and updates tracked automatically.",
    "signature": "",
    "postal_address": "",
    "follow_up_days": "4",
    "last_run": "",
    "opt_out_line": "If this isn't relevant, just reply 'no thanks' and I won't follow up.",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        for table, columns in MIGRATIONS.items():
            existing = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            for name, spec in columns.items():
                if name not in existing:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))


# ---------------------------------------------------------------- settings
def settings() -> dict:
    with connect() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}


def save_settings(values: dict) -> None:
    with connect() as c:
        for k, v in values.items():
            if k in DEFAULT_SETTINGS:
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v.strip()))


def csv_setting(s: dict, key: str) -> list[str]:
    return [x.strip() for x in s.get(key, "").split(",") if x.strip()]


# ---------------------------------------------------------------- leads
def _lead(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["signals"] = json.loads(d["signals"] or "[]")
    d["research"] = json.loads(d["research"]) if d["research"] else None
    d["contacts"] = json.loads(d["contacts"]) if d["contacts"] else None
    return d


def add_lead(name, domain, website, *, description=None, location=None, source=None, source_url=None,
             signals=None, email=None) -> int | None:
    """Insert a lead; returns its id, or None if the domain is already known or blocked."""
    if is_blocked(domain):
        return None
    with connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO leads (name, domain, website, description, location, source, source_url, email, "
            "signals, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, domain, website, description, location, source, source_url, email, json.dumps(signals or []),
             now(), now()))
        return cur.lastrowid if cur.rowcount else None


def get_lead(lead_id: int) -> dict | None:
    with connect() as c:
        return _lead(c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())


def list_leads(status: str | None = None) -> list[dict]:
    with connect() as c:
        if status:
            rows = c.execute("SELECT * FROM leads WHERE status = ? ORDER BY id DESC", (status,))
        else:
            rows = c.execute("SELECT * FROM leads ORDER BY id DESC")
        return [_lead(r) for r in rows]


def update_lead(lead_id: int, **fields) -> None:
    for k in ("research", "contacts", "signals"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE leads SET {cols} WHERE id = ?", (*fields.values(), lead_id))


def delete_lead(lead_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM leads WHERE id = ?", (lead_id,))


def status_counts() -> dict:
    with connect() as c:
        return {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")}


STAGES = ["new", "researched", "needs_contact", "drafted", "contacted", "replied", "meeting", "won", "lost", "skipped",
          "error"]


def follow_ups_due() -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    with connect() as c:
        rows = c.execute("SELECT * FROM leads WHERE follow_up IS NOT NULL AND follow_up <= ? "
                         "AND status NOT IN ('won', 'lost', 'skipped') ORDER BY follow_up", (today,))
        return [_lead(r) for r in rows]


# ---------------------------------------------------------------- notes
def add_note(lead_id: int, body: str) -> None:
    with connect() as c:
        c.execute("INSERT INTO notes (lead_id, body, created_at) VALUES (?, ?, ?)", (lead_id, body, now()))


def notes_for(lead_id: int) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM notes WHERE lead_id = ? ORDER BY id DESC", (lead_id,))]


# ---------------------------------------------------------------- messages
def add_message(lead_id, channel, recipient, subject, body, *, kind="first", drafted_by=None) -> int:
    with connect() as c:
        return c.execute(
            "INSERT INTO messages (lead_id, channel, recipient, subject, body, kind, drafted_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (lead_id, channel, recipient, subject, body, kind, drafted_by, now())).lastrowid


def reject_pending(lead_id: int) -> None:
    with connect() as c:
        c.execute("UPDATE messages SET status = 'rejected' WHERE lead_id = ? AND status = 'pending'", (lead_id,))


def get_message(msg_id: int) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return dict(r) if r else None


def messages_for(lead_id: int) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM messages WHERE lead_id = ? ORDER BY id DESC", (lead_id,))]


def pending_messages() -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT m.*, l.name AS lead_name, l.domain AS lead_domain FROM messages m JOIN leads l ON l.id = m.lead_id "
            "WHERE m.status = 'pending' ORDER BY m.id")
        return [dict(r) for r in rows]


def update_message(msg_id: int, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE messages SET {cols} WHERE id = ?", (*fields.values(), msg_id))


def sent_today() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM messages WHERE status = 'sent' AND channel = 'email' "
                         "AND sent_at >= ?", (today,)).fetchone()[0]


def already_contacted(recipient: str) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM messages WHERE recipient = ? AND status = 'sent'",
                         (recipient,)).fetchone() is not None


def sent_emails() -> list[dict]:
    """Sent mail for leads still awaiting a response, used to match replies and bounces."""
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT m.*, l.domain AS lead_domain, l.status AS lead_status FROM messages m JOIN leads l ON l.id = m.lead_id "
            "WHERE m.channel = 'email' AND m.status = 'sent' AND l.status = 'contacted'")]


def follow_ups_to_draft() -> list[dict]:
    """Contacted leads past their follow-up date, with no follow-up drafted or sent yet."""
    today = datetime.now(timezone.utc).date().isoformat()
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM leads l WHERE status = 'contacted' AND follow_up IS NOT NULL AND follow_up <= ? AND NOT EXISTS "
            "(SELECT 1 FROM messages m WHERE m.lead_id = l.id AND m.kind = 'follow_up' AND m.status != 'rejected')",
            (today,))
        return [_lead(r) for r in rows]


def mail_seen(message_id: str) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM seen_mail WHERE message_id = ?", (message_id,)).fetchone() is not None


def mark_mail_seen(message_id: str) -> None:
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO seen_mail (message_id) VALUES (?)", (message_id,))


# ---------------------------------------------------------------- do-not-contact
def block(value: str) -> None:
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO do_not_contact (value) VALUES (?)", (value.strip().lower(),))


def unblock(value: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM do_not_contact WHERE value = ?", (value,))


def blocked() -> list[str]:
    with connect() as c:
        return [r[0] for r in c.execute("SELECT value FROM do_not_contact ORDER BY value")]


def is_blocked(value: str) -> bool:
    v = (value or "").lower()
    domain = v.split("@")[-1]
    with connect() as c:
        return c.execute("SELECT 1 FROM do_not_contact WHERE value IN (?, ?)", (v, domain)).fetchone() is not None
