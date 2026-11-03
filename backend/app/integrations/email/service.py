"""Mailbox account management, idempotent draft creation and reply sync."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.integrations.email.base import MailboxAuthError, MailboxError, MailboxProvider, TokenSet
from app.integrations.email.gmail import GmailProvider
from app.integrations.email.outlook import OutlookProvider
from app.models import (
    Company,
    Contact,
    DraftStatus,
    EmailAccount,
    EmailDraft,
    LeadStatus,
    OutreachDraft,
    User,
)
from app.models.base import utcnow
from app.services.audit import audit
from app.services.state_machine import try_transition
from app.services.suppression import contact_suppressed

log = logging.getLogger(__name__)
_PROVIDERS: dict[str, MailboxProvider] = {"gmail": GmailProvider(), "outlook": OutlookProvider()}


def get_mailbox_provider(key: str) -> MailboxProvider:
    return _PROVIDERS[key]


def set_mailbox_provider(key: str, p: MailboxProvider) -> None:
    """Test hook."""
    _PROVIDERS[key] = p


def store_tokens(acct: EmailAccount, t: TokenSet) -> None:
    acct.access_token_enc = encrypt(t.access_token)
    if t.refresh_token:
        acct.refresh_token_enc = encrypt(t.refresh_token)
    acct.token_expires_at = t.expires_at
    if t.scopes:
        acct.scopes = t.scopes


def access_token(db: Session, acct: EmailAccount) -> str:
    """Valid access token, refreshing if needed. Marks the account expired/revoked on auth failure."""
    if acct.status in ("revoked",):
        raise MailboxAuthError("Account access was revoked — reconnect it")
    if acct.access_token_enc and acct.token_expires_at and acct.token_expires_at > utcnow() + timedelta(seconds=90):
        return decrypt(acct.access_token_enc)
    if not acct.refresh_token_enc:
        acct.status = "expired"
        raise MailboxAuthError("No refresh token — reconnect the account")
    try:
        t = get_mailbox_provider(acct.provider).refresh(decrypt(acct.refresh_token_enc))
    except MailboxAuthError as e:
        acct.status, acct.last_error = "expired", str(e)
        db.flush()
        raise
    store_tokens(acct, t)
    acct.status, acct.last_error = "connected", None
    db.flush()
    return t.access_token


def default_account(db: Session) -> EmailAccount | None:
    accts = db.scalars(select(EmailAccount).where(EmailAccount.deleted_at.is_(None),
                                                  EmailAccount.status == "connected")
                       .order_by(EmailAccount.is_default.desc(), EmailAccount.created_at)).all()
    return accts[0] if accts else None


def create_mailbox_draft(db: Session, draft: OutreachDraft, account: EmailAccount,
                         user: User | None = None) -> EmailDraft:
    """Create an UNSENT draft in the mailbox. Idempotent: retries never create a second draft."""
    if draft.status not in (DraftStatus.APPROVED, DraftStatus.EMAIL_DRAFT_CREATED):
        raise ValueError("Only approved drafts can be turned into mailbox drafts")
    company = db.get(Company, draft.company_id)
    contact = db.get(Contact, draft.contact_id) if draft.contact_id else None
    if contact is None or not contact.email_normalized:
        raise ValueError("Draft has no recipient email")
    if contact_suppressed(db, contact, company):
        draft.status = DraftStatus.BLOCKED
        db.flush()
        raise ValueError("Recipient is suppressed — draft blocked")
    key = f"age:{draft.id}:{account.id}:v{draft.version}"
    ed = db.scalar(select(EmailDraft).where(EmailDraft.outreach_draft_id == draft.id,
                                            EmailDraft.email_account_id == account.id))
    if ed and ed.status == "created":
        return ed  # already done — duplicate prevented
    if ed is None:
        ed = EmailDraft(outreach_draft_id=draft.id, email_account_id=account.id, contact_id=contact.id,
                        company_id=company.id, idempotency_key=key, to_email=contact.email_normalized,
                        subject=draft.subject, status="pending")
        db.add(ed)
        try:
            db.flush()
        except IntegrityError:  # concurrent creator inserted the row first
            db.rollback()
            raise MailboxError("Draft creation already in progress", retryable=True) from None
    # Atomic claim, committed BEFORE calling the provider: a concurrent worker cannot claim the same row,
    # and if we crash mid-call the next attempt (attempts > 1) first looks the draft up by its key.
    now = utcnow()
    claimed = db.execute(update(EmailDraft).where(
        EmailDraft.id == ed.id,
        or_(EmailDraft.status.in_(["pending", "failed"]),
            and_(EmailDraft.status == "in_progress", EmailDraft.updated_at < now - timedelta(minutes=5))),
    ).values(status="in_progress", attempts=EmailDraft.attempts + 1, updated_at=now)).rowcount
    db.commit()
    if not claimed:
        db.refresh(ed)
        if ed.status == "created":
            return ed
        raise MailboxError("Draft creation already in progress", retryable=True)
    db.refresh(ed)
    provider = get_mailbox_provider(account.provider)
    try:
        token = access_token(db, account)
        created = None
        if ed.attempts > 1:
            created = provider.find_draft_by_key(token, ed.idempotency_key)
        if created is None:
            created = provider.create_draft(token, to=contact.email_normalized, subject=draft.subject, body=draft.body,
                                            from_email=account.email, idempotency_key=ed.idempotency_key)
    except (MailboxAuthError, MailboxError) as e:
        ed.status, ed.last_error = "failed", str(e)[:1000]
        account.last_error = str(e)[:1000]
        db.commit()
        raise
    ed.status = "created"
    ed.external_draft_id, ed.external_message_id = created.draft_id, created.message_id
    ed.external_thread_id, ed.internet_message_id = created.thread_id, created.internet_message_id
    ed.last_error = None
    draft.status = DraftStatus.EMAIL_DRAFT_CREATED
    try_transition(db, company, LeadStatus.EMAIL_DRAFT_CREATED, actor=user, reason="unsent mailbox draft created")
    audit(db, "email_draft.created", actor=user, entity_type="outreach_draft", entity_id=draft.id,
          detail={"provider": account.provider, "account": account.email, "external_draft_id": created.draft_id,
                  "sent": False})
    db.flush()
    return ed
