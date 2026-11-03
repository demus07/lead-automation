from __future__ import annotations

import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import get_or_404
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_admin, require_operator, require_viewer
from app.core.security import sign_state, verify_state
from app.integrations.email.base import MailboxAuthError, MailboxError
from app.integrations.email.service import get_mailbox_provider, store_tokens
from app.models import EmailAccount, User
from app.models.base import utcnow
from app.schemas.common import Msg
from app.services.audit import audit

router = APIRouter(prefix="/api/email", tags=["email"])
PROVIDERS = ("gmail", "outlook")


def redirect_uri(provider: str) -> str:
    return f"{get_settings().public_api_url.rstrip('/')}/api/email/oauth/{provider}/callback"


def acct_out(a: EmailAccount) -> dict:
    return {"id": a.id, "provider": a.provider, "email": a.email, "display_name": a.display_name, "status": a.status,
            "scopes": a.scopes, "is_default": a.is_default, "last_error": a.last_error,
            "last_synced_at": a.last_synced_at, "token_expires_at": a.token_expires_at, "created_at": a.created_at}


@router.get("/accounts")
def accounts(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    rows = db.scalars(select(EmailAccount).where(EmailAccount.deleted_at.is_(None)).order_by(EmailAccount.created_at)).all()
    return {
        "accounts": [acct_out(a) for a in rows],
        "providers": [{"key": p, "configured": get_mailbox_provider(p).configured(),
                       "scopes": get_mailbox_provider(p).scopes, "redirect_uri": redirect_uri(p),
                       "requires": "GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET" if p == "gmail"
                       else "MICROSOFT_CLIENT_ID/MICROSOFT_CLIENT_SECRET"} for p in PROVIDERS],
        "sending": "disabled — the application only creates unsent drafts",
    }


@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, user: User = Depends(require_admin)):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    p = get_mailbox_provider(provider)
    if not p.configured():
        raise HTTPException(400, f"{provider} OAuth client is not configured on the server")
    state = sign_state(f"{provider}:{user.id}:{secrets.token_urlsafe(8)}:{int(time.time())}")
    return {"url": p.authorize_url(state, redirect_uri(provider))}


@router.get("/oauth/{provider}/callback")
def oauth_callback(provider: str, code: str | None = None, state: str | None = None, error: str | None = None,
                   db: Session = Depends(get_db)):
    app_url = get_settings().public_app_url.rstrip("/")
    back = f"{app_url}/settings/integrations"
    if error or not code or not state:
        return RedirectResponse(f"{back}?error={error or 'missing_code'}")
    data = verify_state(state)
    if not data:
        return RedirectResponse(f"{back}?error=invalid_state")
    prov, user_id, _, ts = data.split(":")
    if prov != provider or time.time() - int(ts) > 900:
        return RedirectResponse(f"{back}?error=expired_state")
    user = db.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        return RedirectResponse(f"{back}?error=invalid_user")
    p = get_mailbox_provider(provider)
    try:
        tokens = p.exchange_code(code, redirect_uri(provider))
        email, name = p.account_identity(tokens.access_token)
    except (MailboxAuthError, MailboxError) as e:
        return RedirectResponse(f"{back}?error=exchange_failed&detail={str(e)[:80]}")
    acct = db.scalar(select(EmailAccount).where(EmailAccount.provider == provider, EmailAccount.email == email.lower()))
    if acct is None:
        acct = EmailAccount(provider=provider, email=email.lower())
        db.add(acct)
    acct.deleted_at = None
    acct.display_name, acct.status, acct.last_error = name, "connected", None
    acct.connected_by_id = user.id
    store_tokens(acct, tokens)
    if not db.scalar(select(EmailAccount).where(EmailAccount.is_default.is_(True), EmailAccount.deleted_at.is_(None))):
        acct.is_default = True
    db.flush()
    audit(db, "email_account.connected", actor=user, entity_type="email_account", entity_id=acct.id,
          detail={"provider": provider, "email": email, "scopes": tokens.scopes})
    db.commit()
    return RedirectResponse(f"{back}?connected={provider}")


@router.post("/accounts/{account_id}/default", response_model=Msg)
def set_default(account_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    a = get_or_404(db, EmailAccount, account_id)
    for other in db.scalars(select(EmailAccount)):
        other.is_default = other.id == a.id
    db.commit()
    return Msg(message=f"{a.email} is now the default drafting account")


@router.delete("/accounts/{account_id}", response_model=Msg)
def disconnect(account_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    a = get_or_404(db, EmailAccount, account_id)
    a.access_token_enc = a.refresh_token_enc = None
    a.status, a.deleted_at, a.is_default = "revoked", utcnow(), False
    audit(db, "email_account.disconnected", actor=user, entity_type="email_account", entity_id=a.id)
    db.commit()
    return Msg(message="Account disconnected and tokens deleted. You can also revoke access in your Google/Microsoft account.")


@router.post("/accounts/{account_id}/sync")
def sync(account_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    from app.workflows import load_workflows
    from app.workflows.engine import start_job

    load_workflows()
    a = get_or_404(db, EmailAccount, account_id)
    job, _ = start_job(db, "replies", params={"account_id": str(a.id)}, user=user)
    db.refresh(job)
    return {"job_id": str(job.id), "status": job.status.value, "stats": job.stats}
