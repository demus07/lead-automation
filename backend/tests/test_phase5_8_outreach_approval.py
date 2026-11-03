import re
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import respx
from httpx import Response

from app.ai.llm.providers import FakeProvider, set_provider_override
from app.core.crypto import encrypt
from app.integrations.email.base import CreatedDraft, MailboxError, ThreadMessage
from app.integrations.email.gmail import GmailProvider
from app.integrations.email.outlook import OutlookProvider
from app.integrations.email.service import set_mailbox_provider
from app.models import (
    AutomationJob,
    Company,
    Contact,
    DraftStatus,
    EmailAccount,
    EmailDraft,
    Interaction,
    JobStatus,
    LeadStatus,
    OutreachDraft,
    Suppression,
)
from app.models.base import utcnow
from app.research import email_verify
from app.research.contact_service import find_contacts
from app.research.fetcher import reset_caches
from app.research.service import research_company
from app.services import settings_service as ss
from app.services.companies import upsert_company
from app.services.outreach import OutreachBlocked, generate_draft
from app.services.scoring import score_company
from tests.helpers import SITE, ScriptedLLM, _outreach, mock_site

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _env(monkeypatch, db):
    reset_caches()
    monkeypatch.setattr(email_verify, "mx_records", lambda d: ["mx"])
    ss.update_section(db, "research", {"request_delay_seconds": 0})
    ss.update_section(db, "agency_profile", {"agency_name": "Studio North", "sender_name": "Sam",
                                             "include_opt_out_line": False, "onboarding_completed": True})
    db.commit()
    yield
    set_provider_override(None)
    set_mailbox_provider("gmail", GmailProvider())
    set_mailbox_provider("outlook", OutlookProvider())


def qualified_company(db, llm=None) -> Company:
    set_provider_override(FakeProvider(llm or ScriptedLLM()))
    with respx.mock(assert_all_called=False) as router:
        mock_site(router)
        c = upsert_company(db, name="Acme Robotics", domain="acme-test.example", website=SITE,
                           fields={"size_range": "51-200"}).company
        db.commit()
        research_company(db, c, force=True)
        find_contacts(db, c)
        score_company(db, c)
        db.commit()
    assert c.status == LeadStatus.QUALIFIED
    return c


def make_account(db, provider="gmail") -> EmailAccount:
    a = EmailAccount(provider=provider, email="sam@studionorth.example", status="connected", is_default=True,
                     access_token_enc=encrypt("tok"), refresh_token_enc=encrypt("refresh"),
                     token_expires_at=utcnow() + timedelta(hours=1), scopes=GmailProvider.scopes)
    db.add(a)
    db.commit()
    return a


class FakeMailbox(GmailProvider):
    """Records calls; deliberately has no send capability (none exists in the interface)."""

    def __init__(self):
        self.created: list[dict] = []
        self.fail_after_create = False
        self.thread: list[ThreadMessage] = []

    def configured(self):
        return True

    def create_draft(self, access_token, *, to, subject, body, from_email, idempotency_key):
        self.created.append({"to": to, "subject": subject, "key": idempotency_key})
        if self.fail_after_create:
            self.fail_after_create = False
            raise MailboxError("timeout after server accepted request", retryable=True)
        return CreatedDraft(f"d{len(self.created)}", f"m{len(self.created)}", "thread-1")

    def find_draft_by_key(self, access_token, idempotency_key):
        for i, c in enumerate(self.created, start=1):
            if c["key"] == idempotency_key:
                return CreatedDraft(f"d{i}", f"m{i}", "thread-1")
        return None

    def thread_messages(self, access_token, thread_id, my_email):
        return self.thread


# ------------------------------------------------------------------ TEST 10
def test_T10_generates_personalised_draft(db):
    c = qualified_company(db)
    d = generate_draft(db, c)
    db.commit()
    assert d.status == DraftStatus.PENDING_APPROVAL, d.quality_report
    assert d.service == "company_brain"
    assert "Jane" in d.body and "Knowledge Manager" in d.body
    assert d.contact.full_name == "Jane Doe"
    assert d.subject and d.linkedin_connection_note and d.linkedin_message and d.recommended_offer
    assert all(cl["evidence_ids"] for cl in d.evidence) and all(cl["sources"][0]["url"] for cl in d.evidence)
    assert d.quality_score >= 75
    assert c.status == LeadStatus.PENDING_APPROVAL


# ------------------------------------------------------------------ TEST 11
def test_T11_quality_catches_unsupported_claims(db):
    def bad(req):
        o = _outreach(req)
        o["body"] = o["body"].replace("Saw you're hiring", "Congrats on raising $40M in your Series B and hiring")
        o["claims"].append({"text": "Raised $40M Series B", "evidence_ids": []})
        return o

    c = qualified_company(db, ScriptedLLM(outreach=bad))
    d = generate_draft(db, c)
    db.commit()
    assert d.status == DraftStatus.NEEDS_REVIEW
    assert d.regeneration_count == 2  # regenerated up to the limit, still failing
    issues = d.quality_report["issues"]
    assert any(i["check"] == "unsupported_claim" and "$40M" in i["text"] for i in issues)
    assert d.quality_score < d.quality_report["threshold"]
    superseded = db.query(OutreachDraft).filter_by(company_id=c.id, status=DraftStatus.SUPERSEDED).count()
    assert superseded == 2


def test_quality_catches_wrong_recipient_and_wrong_service(db):
    def wrong(req):
        o = _outreach(req)
        o["body"] = o["body"].replace("Hi Jane", "Hi Marco") + "\nWe also do bespoke website redesigns."
        return o

    c = qualified_company(db, ScriptedLLM(outreach=wrong))
    ss.update_section(db, "quality", {"max_regenerations": 0})
    d = generate_draft(db, c)
    checks = {i["check"] for i in d.quality_report["issues"]}
    assert {"recipient_name", "service"} <= checks and d.status == DraftStatus.NEEDS_REVIEW


# ------------------------------------------------------------------ TEST 12 + 13
def test_T12_T13_queue_edit_and_approve(operator_client, db):
    c = qualified_company(db)
    generate_draft(db, c)
    db.commit()
    q = operator_client.get("/api/approvals/queue").json()
    assert q["total"] == 1
    item = q["items"][0]
    for field in ("subject", "body", "linkedin_message", "quality_score", "evidence", "research_summary"):
        assert item[field]
    assert item["company"]["name"] == "Acme Robotics" and item["company"]["website_score"] is not None
    assert item["contact"]["full_name"] == "Jane Doe" and item["contact"]["email"] == "jane.doe@acme-test.example"
    did = item["id"]
    new_body = item["body"].replace("Would a 20-minute call", "Would a short call")
    r = operator_client.patch(f"/api/drafts/{did}", json={"body": new_body, "comment": "tweak CTA"})
    assert r.status_code == 200 and r.json()["edited_by_user"] is True
    assert r.json()["quality_report"]["after_human_edit"] is True
    r = operator_client.post(f"/api/approvals/{did}/approve", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approved"] is True and body["email_draft"] is None and "No email account" in body["message"]
    d = db.get(OutreachDraft, uuid.UUID(did))
    db.refresh(d)
    assert d.status == DraftStatus.APPROVED and d.approved_by_id is not None
    actions = [h["action"] for h in r.json()["draft"]["history"]]
    assert actions == ["edit", "approve"]


def test_viewer_cannot_approve(viewer_client, db):
    c = qualified_company(db)
    d = generate_draft(db, c)
    db.commit()
    assert viewer_client.post(f"/api/approvals/{d.id}/approve", json={}).status_code == 403


def test_needs_review_requires_override(operator_client, db):
    c = qualified_company(db)
    ss.update_section(db, "quality", {"threshold": 101, "max_regenerations": 0})
    d = generate_draft(db, c)
    db.commit()
    assert d.status == DraftStatus.NEEDS_REVIEW
    assert operator_client.post(f"/api/approvals/{d.id}/approve", json={}).status_code == 409
    r = operator_client.post(f"/api/approvals/{d.id}/approve", json={"override_quality": True, "comment": "checked"})
    assert r.status_code == 200


# ------------------------------------------------------------------ TEST 14, 15, 16 (Gmail API mocked over HTTP)
@respx.mock
def test_T14_T15_T16_gmail_unsent_draft_no_send_no_duplicates(operator_client, db):
    c = qualified_company(db)
    d = generate_draft(db, c)
    db.commit()
    acct = make_account(db, "gmail")
    create = respx.post("https://gmail.googleapis.com/gmail/v1/users/me/drafts").mock(
        return_value=Response(200, json={"id": "r-123", "message": {"id": "m-1", "threadId": "t-1"}}))
    send_routes = respx.route(url__regex=r".*/send.*").mock(return_value=Response(500))
    r = operator_client.post(f"/api/approvals/{d.id}/approve", json={"email_account_id": str(acct.id)})
    assert r.status_code == 200, r.text
    assert r.json()["email_draft"]["external_draft_id"] == "r-123"
    # TEST 14: draft created with recipient + subject
    assert create.call_count == 1
    import base64
    import json as _json

    raw = _json.loads(create.calls[0].request.content)["message"]["raw"]
    mime = base64.urlsafe_b64decode(raw).decode()
    assert "To: jane.doe@acme-test.example" in mime and "X-AGE-Draft-Key" in mime
    # TEST 15: nothing was sent
    assert send_routes.call_count == 0
    assert all("/send" not in str(call.request.url) for call in respx.calls)
    ed = db.query(EmailDraft).one()
    assert ed.status == "created" and ed.sent_detected_at is None
    db.refresh(c)
    assert c.status == LeadStatus.EMAIL_DRAFT_CREATED
    # TEST 16: repeated approval / workflow retries do not create another draft
    r2 = operator_client.post(f"/api/approvals/{d.id}/approve", json={"email_account_id": str(acct.id)})
    assert r2.status_code == 200
    operator_client.post("/api/workflows/approval/run", json={"params": {}})
    assert create.call_count == 1
    assert db.query(EmailDraft).count() == 1


@respx.mock
def test_T14_outlook_draft_created_via_graph_without_send(operator_client, db):
    c = qualified_company(db)
    d = generate_draft(db, c)
    db.commit()
    acct = make_account(db, "outlook")
    create = respx.post("https://graph.microsoft.com/v1.0/me/messages").mock(return_value=Response(
        201, json={"id": "AAMk1", "conversationId": "conv-1", "internetMessageId": "<x@y>", "isDraft": True}))
    r = operator_client.post(f"/api/approvals/{d.id}/approve", json={"email_account_id": str(acct.id)})
    assert r.status_code == 200 and r.json()["email_draft"]["external_draft_id"] == "AAMk1"
    assert create.call_count == 1
    assert not any("sendMail" in str(c.request.url) or str(c.request.url).endswith("/send") for c in respx.calls)
    assert "Mail.Send" not in OutlookProvider.scopes


def test_T16_crash_after_remote_create_does_not_duplicate(operator_client, db):
    c = qualified_company(db)
    d = generate_draft(db, c)
    db.commit()
    fake = FakeMailbox()
    fake.fail_after_create = True
    set_mailbox_provider("gmail", fake)
    make_account(db)
    r = operator_client.post(f"/api/approvals/{d.id}/approve", json={})
    assert "retried" in r.json()["message"]
    assert len(fake.created) == 1
    # background retry recovers the existing draft by its idempotency key instead of creating a new one
    operator_client.post("/api/workflows/approval/run", json={"params": {}})
    assert len(fake.created) == 1
    ed = db.query(EmailDraft).one()
    db.refresh(ed)
    assert ed.status == "created" and ed.external_draft_id == "d1" and ed.attempts == 2


def test_T15_no_send_code_paths_exist():
    """Static guarantee: the codebase never calls a send endpoint of Gmail or Microsoft Graph."""
    forbidden = re.compile(r"(drafts/send|messages/send|/sendMail|drafts\.send|messages\.send|\"/send\"|'/send')")
    offenders = []
    for p in (BACKEND / "app").rglob("*.py"):
        text = p.read_text()
        for m in forbidden.finditer(text):
            line = text[: m.start()].count("\n") + 1
            offenders.append(f"{p.relative_to(BACKEND)}:{line}")
    assert offenders == []
    assert not hasattr(GmailProvider, "send") and not hasattr(OutlookProvider, "send")


# ------------------------------------------------------------------ TEST 17 + reply intelligence
def test_T17_opt_out_reply_adds_suppression_via_mailbox_sync(operator_client, db):
    c = qualified_company(db)
    d = generate_draft(db, c)
    db.commit()
    fake = FakeMailbox()
    set_mailbox_provider("gmail", fake)
    acct = make_account(db)
    operator_client.post(f"/api/approvals/{d.id}/approve", json={})
    fake.thread = [
        ThreadMessage("m1", "sam@studionorth.example", "jane.doe@acme-test.example", "Hi", "Hi Jane", utcnow(),
                      False, True),
        ThreadMessage("m2", "jane.doe@acme-test.example", "sam@studionorth.example", "Re: Hi",
                      "Please remove me from your mailing list.", utcnow(), False, False),
    ]
    r = operator_client.post(f"/api/email/accounts/{acct.id}/sync")
    assert r.status_code == 200, r.text
    sup = db.query(Suppression).filter_by(kind="email", value="jane.doe@acme-test.example").one()
    assert sup.reason == "opt_out" and sup.active
    jane = db.query(Contact).filter_by(email_normalized="jane.doe@acme-test.example").one()
    assert jane.status == "do_not_contact"
    inbound = db.query(Interaction).filter_by(direction="inbound").one()
    assert inbound.classification == "unsubscribe" and inbound.suggested_reply is None
    db.refresh(c)
    assert c.status == LeadStatus.NOT_INTERESTED
    # sync is idempotent
    operator_client.post(f"/api/email/accounts/{acct.id}/sync")
    assert db.query(Interaction).filter_by(direction="inbound").count() == 1


def test_reply_meeting_request_creates_task(operator_client, db):
    c = qualified_company(db)
    jane = db.query(Contact).filter_by(full_name="Jane Doe").one()
    r = operator_client.post("/api/conversations/inbound", json={
        "company_id": str(c.id), "contact_id": str(jane.id), "channel": "linkedin",
        "body": "Thanks Sam — happy to chat. Could we set up a call next week?"})
    assert r.status_code == 200, r.text
    assert r.json()["classification"] == "meeting_requested"
    assert r.json()["suggested_reply"]
    tasks = operator_client.get("/api/tasks").json()["items"]
    assert any("meeting requested" in t["title"] for t in tasks)


# ------------------------------------------------------------------ TEST 18
def test_T18_suppressed_contacts_get_no_new_drafts(operator_client, db):
    c = qualified_company(db)
    d = generate_draft(db, c)
    db.commit()
    jane = db.query(Contact).filter_by(full_name="Jane Doe").one()
    r = operator_client.post(f"/api/contacts/{jane.id}/do-not-contact", json={"reason": "opt_out"})
    assert r.status_code == 200
    db.refresh(d)
    assert d.status == DraftStatus.BLOCKED  # pending draft blocked immediately
    with pytest.raises(OutreachBlocked):
        generate_draft(db, c, contact=jane)
    r = operator_client.post("/api/drafts/generate", json={"company_id": str(c.id), "contact_id": str(jane.id)})
    assert r.status_code == 409
    # Domain-level suppression blocks everyone at the company
    db.add(Suppression(kind="domain", value="acme-test.example", reason="manual"))
    db.commit()
    with pytest.raises(OutreachBlocked):
        generate_draft(db, c)
    assert operator_client.post(f"/api/approvals/{d.id}/approve", json={}).status_code == 409


# ------------------------------------------------------------------ TEST 19
def test_T19_dashboard_shows_real_records(operator_client, db):
    c = qualified_company(db)
    generate_draft(db, c)
    db.commit()
    dash = operator_client.get("/api/dashboard").json()
    assert dash["kpis"]["companies"] == db.query(Company).filter(Company.deleted_at.is_(None)).count() == 1
    assert dash["kpis"]["pending_approval"] == 1
    assert dash["pending_drafts"][0]["company_name"] == "Acme Robotics"
    assert dash["top_opportunities"][0]["name"] == "Acme Robotics"
    assert dash["recent_jobs"] == [] or isinstance(dash["recent_jobs"], list)
    an = operator_client.get("/api/analytics").json()
    assert an["funnel"][0]["count"] == 1 and an["by_service"].get("company_brain") == 1
    usage = operator_client.get("/api/ai/usage").json()
    assert usage["totals"]["calls"] > 0 and {"website_research", "opportunity_scoring", "outreach_generation"} <= {
        a["agent"] for a in usage["by_agent"]}


# ------------------------------------------------------------------ TEST 20
def test_T20_background_job_recovers_from_temporary_failure(db):
    from app.workflows import load_workflows
    from app.workflows.engine import RetryableError, execute_job, start_job, workflow

    load_workflows()
    calls = {"n": 0}

    @workflow("flaky_test", "test")
    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryableError("temporary network blip")
        return {"ok": True}

    job, _ = start_job(db, "flaky_test", idempotency_key="flaky-1")
    db.expire_all()
    job = db.get(AutomationJob, job.id)
    assert job.status == JobStatus.QUEUED and job.next_retry_at is not None and job.errors
    assert execute_job(job.id) == JobStatus.SUCCEEDED
    db.expire_all()
    job = db.get(AutomationJob, job.id)
    assert job.attempts == 2 and job.stats == {"ok": True}
    # idempotent start returns the same job
    again, created = start_job(db, "flaky_test", idempotency_key="flaky-1")
    assert not created and again.id == job.id


def test_T20_stale_running_job_is_recovered(db):
    from app.workflows import load_workflows
    from app.workflows.recovery import recover

    load_workflows()
    j = AutomationJob(workflow="maintenance", status=JobStatus.RUNNING, attempts=1, max_attempts=3,
                      started_at=utcnow() - timedelta(hours=3))
    db.add(j)
    db.commit()
    recover(db)
    db.expire_all()
    j = db.get(AutomationJob, j.id)
    assert j.status == JobStatus.SUCCEEDED  # re-queued and (eager mode) re-executed
    assert any("recovered" in e["error"] for e in j.errors)


def test_workflow_pause_skips_scheduled_runs(admin_client, db):
    from app.workflows.scheduler import tick

    admin_client.get("/api/workflows")
    admin_client.patch("/api/workflows/maintenance/schedule", json={"paused": True})
    from app.models import WorkflowSchedule

    s = db.query(WorkflowSchedule).filter_by(workflow="maintenance").one()
    s.next_run_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert tick(db) == []
    admin_client.patch("/api/workflows/maintenance/schedule", json={"paused": False})
    s = db.query(WorkflowSchedule).filter_by(workflow="maintenance").one()
    s.next_run_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert tick(db) == ["maintenance"]
    assert tick(db) == []  # slot already consumed (idempotent)
