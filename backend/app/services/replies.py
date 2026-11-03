"""Reply monitoring, classification and follow-up suggestions. Never sends replies."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.sanitize import wrap_untrusted
from app.integrations.email.base import MailboxAuthError, MailboxError
from app.models import Company, Contact, EmailAccount, EmailDraft, Interaction, LeadStatus, Task
from app.models.base import utcnow
from app.services.audit import audit
from app.services.state_machine import try_transition
from app.services.suppression import suppress

log = logging.getLogger(__name__)

OPT_OUT = re.compile(r"\b(unsubscribe|remove me|take me off|opt[- ]?out|stop (emailing|contacting|sending)|"
                     r"do not (contact|email)|don'?t (contact|email) me|no further (contact|emails)|"
                     r"not interested[,.]? (please )?(don'?t|do not) follow)", re.I)
OOO = re.compile(r"\b(out of (the )?office|on (annual )?leave|on vacation|away until|currently away|"
                 r"limited access to (my )?email|abwesend|absence)\b", re.I)
AUTO = re.compile(r"\b(auto(matic)?[- ]?reply|do not reply|noreply|this is an automated|delivery status notification|"
                  r"undeliverable|mail delivery (failed|subsystem))\b", re.I)
MEETING = re.compile(r"\b(book a (time|call)|calendly|schedule (a )?(call|meeting)|free (on|next)|"
                     r"let'?s (talk|chat|meet)|happy to (chat|talk|meet)|send (me )?(some )?times)\b", re.I)
NOT_INTERESTED = re.compile(r"\b(not interested|no thanks|no thank you|not a fit|not relevant|we'?re all set|"
                            r"not at this time|pass on this)\b", re.I)

STATUS_FOR_LABEL = {
    "interested": LeadStatus.INTERESTED, "meeting_requested": LeadStatus.MEETING_REQUESTED,
    "needs_information": LeadStatus.INTERESTED, "not_interested": LeadStatus.NOT_INTERESTED,
    "unsubscribe": LeadStatus.NOT_INTERESTED, "objection": LeadStatus.REPLIED,
}


def rule_classify(subject: str | None, text: str | None, auto_submitted: str | None = None) -> dict[str, Any] | None:
    t = f"{subject or ''}\n{text or ''}"
    if OPT_OUT.search(t):
        return {"label": "unsubscribe", "confidence": 0.95, "opt_out_requested": True, "method": "rule"}
    if auto_submitted and auto_submitted.lower() != "no":
        return {"label": "automatic_reply", "confidence": 0.9, "opt_out_requested": False, "method": "rule"}
    if OOO.search(t):
        return {"label": "out_of_office", "confidence": 0.85, "opt_out_requested": False, "method": "rule"}
    if AUTO.search(t):
        return {"label": "automatic_reply", "confidence": 0.8, "opt_out_requested": False, "method": "rule"}
    if NOT_INTERESTED.search(t):
        return {"label": "not_interested", "confidence": 0.7, "opt_out_requested": False, "method": "rule"}
    if MEETING.search(t):
        return {"label": "meeting_requested", "confidence": 0.65, "opt_out_requested": False, "method": "rule"}
    return None


def classify(db: Session, interaction: Interaction, company: Company | None, job_id=None) -> dict[str, Any]:
    from app.ai.agents.context import agency_context
    from app.ai.agents.schemas import ReplyOutput
    from app.ai.llm.providers import llm_available
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, load_prompt, run_agent
    from app.services import settings_service

    rule = rule_classify(interaction.subject, interaction.snippet,
                         (interaction.classification_detail or {}).get("auto_submitted"))
    result: dict[str, Any] = rule or {"label": "unknown", "confidence": 0.3, "opt_out_requested": False, "method": "rule"}
    if llm_available(settings_service.get_section(db, "llm")) and (rule is None or rule["label"] not in (
            "unsubscribe", "automatic_reply", "out_of_office")):
        user = (f"Our outreach was to {company.name if company else 'a prospect'}.\nReply subject: "
                f"{interaction.subject}\n" + wrap_untrusted(interaction.snippet or "", source="email", kind="email"))
        try:
            res = run_agent(db, agent="reply_classification",
                            system=load_prompt("reply_classification").replace("{agency_context}", agency_context(db)),
                            user=user, schema=ReplyOutput, tier="fast",
                            company_id=company.id if company else None, job_id=job_id)
            o = res.output
            result = {"label": o.label, "confidence": o.confidence, "summary": o.summary,
                      "opt_out_requested": o.opt_out_requested or bool(rule and rule["opt_out_requested"]),
                      "suggested_reply": None if o.opt_out_requested else o.suggested_reply,
                      "suggested_action": o.suggested_action, "method": "llm", "ai_run_id": str(res.run_id)}
        except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
            result["note"] = f"AI classification unavailable: {e}"
    if result.get("opt_out_requested"):
        result["label"] = "unsubscribe"
        result["suggested_reply"] = None
    result.setdefault("suggested_action", {
        "unsubscribe": "Contact suppressed automatically — no further outreach.",
        "out_of_office": "Wait until they are back; no action needed.",
        "automatic_reply": "No action needed.",
        "not_interested": "Close the lead; consider revisiting in 6–12 months if appropriate.",
        "meeting_requested": "Reply with times or a booking link.",
    }.get(result["label"], "Review the reply and respond personally."))
    return result


def apply_classification(db: Session, interaction: Interaction, result: dict[str, Any], user=None) -> None:
    interaction.classification = result["label"]
    interaction.classification_confidence = result.get("confidence")
    interaction.classification_detail = {**(interaction.classification_detail or {}), **result}
    interaction.suggested_reply = result.get("suggested_reply")
    interaction.suggested_action = result.get("suggested_action")
    company = db.get(Company, interaction.company_id) if interaction.company_id else None
    contact = db.get(Contact, interaction.contact_id) if interaction.contact_id else None
    if result.get("opt_out_requested") or result["label"] == "unsubscribe":
        suppress(db, email=interaction.from_email or (contact.email if contact else None), reason="opt_out",
                 source=f"reply {interaction.external_message_id or interaction.id}", contact=contact,
                 company=None, user=user)
    if company and result["label"] not in ("out_of_office", "automatic_reply", "unknown"):
        try_transition(db, company, LeadStatus.CONTACTED, reason="reply received")
        try_transition(db, company, LeadStatus.REPLIED, reason="reply received")
        target = STATUS_FOR_LABEL.get(result["label"])
        if target and target != LeadStatus.REPLIED:
            try_transition(db, company, target, reason=f"reply classified {result['label']}")
    if company and result["label"] in ("interested", "meeting_requested", "needs_information", "objection"):
        db.add(Task(title=f"Respond to {contact.full_name if contact else company.name} ({result['label'].replace('_', ' ')})",
                    description=(result.get("suggested_reply") or result.get("suggested_action") or "")[:5000],
                    company_id=company.id, contact_id=contact.id if contact else None,
                    due_at=utcnow() + timedelta(days=1), kind="reply"))
    audit(db, "reply.classified", actor=user, actor_type=None if user else "agent", entity_type="interaction",
          entity_id=interaction.id, detail={"label": result["label"], "method": result.get("method")})
    db.flush()


def sync_account(db: Session, account: EmailAccount, *, max_threads: int = 200, job_id=None) -> dict[str, Any]:
    from app.integrations.email.service import access_token, get_mailbox_provider

    stats = {"threads": 0, "sent_detected": 0, "new_replies": 0, "errors": 0}
    provider = get_mailbox_provider(account.provider)
    try:
        token = access_token(db, account)
    except MailboxAuthError as e:
        stats["error"] = str(e)
        return stats
    since = utcnow() - timedelta(days=120)
    eds = db.scalars(select(EmailDraft).where(
        EmailDraft.email_account_id == account.id, EmailDraft.status.in_(["created", "sent_by_user"]),
        EmailDraft.external_thread_id.is_not(None), EmailDraft.created_at >= since)
        .order_by(EmailDraft.created_at.desc()).limit(max_threads)).all()
    for ed in eds:
        stats["threads"] += 1
        try:
            msgs = provider.thread_messages(token, ed.external_thread_id, account.email)
        except MailboxAuthError:
            account.status = "expired"
            stats["error"] = "auth"
            break
        except MailboxError as e:
            stats["errors"] += 1
            log.info("thread fetch failed: %s", e)
            continue
        company = db.get(Company, ed.company_id) if ed.company_id else None
        contact = db.get(Contact, ed.contact_id) if ed.contact_id else None
        for m in sorted(msgs, key=lambda x: x.date or utcnow()):
            if m.is_draft:
                continue
            if m.is_sent_by_me:
                if ed.sent_detected_at is None:
                    ed.sent_detected_at = m.date or utcnow()
                    ed.status = "sent_by_user"
                    stats["sent_detected"] += 1
                    _record(db, account, ed, m, "outbound", company, contact)
                    if company:
                        try_transition(db, company, LeadStatus.CONTACTED, reason="user sent the email manually")
                        db.add(Task(title=f"Follow up with {contact.full_name if contact else company.name} if no reply",
                                    description="Check the thread; if there is no reply, consider a short, specific "
                                                "follow-up (drafts still require approval).",
                                    company_id=company.id, contact_id=contact.id if contact else None,
                                    due_at=(m.date or utcnow()) + timedelta(days=5), kind="follow_up"))
                continue
            inter = _record(db, account, ed, m, "inbound", company, contact)
            if inter is None:
                continue  # already processed
            stats["new_replies"] += 1
            result = classify(db, inter, company, job_id)
            apply_classification(db, inter, result)
        db.commit()
    account.last_synced_at = utcnow()
    db.flush()
    return stats


def _record(db, account, ed, m, direction, company, contact) -> Interaction | None:
    existing = db.scalar(select(Interaction).where(Interaction.email_account_id == account.id,
                                                   Interaction.external_message_id == m.message_id))
    if existing:
        return None
    inter = Interaction(company_id=company.id if company else None, contact_id=contact.id if contact else None,
                        email_account_id=account.id, email_draft_id=ed.id, channel="email", direction=direction,
                        external_message_id=m.message_id, external_thread_id=ed.external_thread_id,
                        from_email=m.from_email, to_email=m.to_email, subject=m.subject,
                        snippet=(m.snippet or "")[:4000], occurred_at=m.date or utcnow(),
                        classification_detail={"auto_submitted": (m.raw or {}).get("auto_submitted")})
    db.add(inter)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        return None
    return inter


def log_manual_inbound(db: Session, *, company: Company, contact: Contact | None, channel: str, subject: str | None,
                       body: str, occurred_at: datetime | None, user=None) -> Interaction:
    inter = Interaction(company_id=company.id, contact_id=contact.id if contact else None, channel=channel,
                        direction="inbound", from_email=contact.email_normalized if contact else None,
                        subject=subject, snippet=body[:4000], occurred_at=occurred_at or utcnow())
    db.add(inter)
    db.flush()
    apply_classification(db, inter, classify(db, inter, company), user=user)
    return inter
