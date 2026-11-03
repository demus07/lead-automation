"""Microsoft Outlook / Microsoft 365 via Microsoft Graph (OAuth2, delegated).

Scopes: offline_access, openid, email, User.Read, Mail.ReadWrite. Mail.Send is deliberately NOT
requested, so the app is technically unable to send mail from the mailbox."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.integrations.email.base import (
    CreatedDraft,
    MailboxAuthError,
    MailboxError,
    MailboxProvider,
    ThreadMessage,
    TokenSet,
)

GRAPH = "https://graph.microsoft.com/v1.0"
# Custom extended property (string, named) used to tag drafts with our idempotency key.
KEY_PROP = "String {6b1d8f3a-7c2e-4b8e-9a51-2f0e3c9d4a10} Name AGEDraftKey"


def _check(r: httpx.Response) -> None:
    if r.status_code == 401:
        raise MailboxAuthError("Microsoft Graph access token rejected")
    if r.status_code == 429 or r.status_code >= 500:
        raise MailboxError(f"Graph HTTP {r.status_code}", retryable=True)
    if r.status_code >= 400:
        raise MailboxError(f"Graph HTTP {r.status_code}: {r.text[:300]}", retryable=False)


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


class OutlookProvider(MailboxProvider):
    key = "outlook"
    scopes = ["offline_access", "openid", "email", "User.Read", "Mail.ReadWrite"]

    def _base(self) -> str:
        return f"https://login.microsoftonline.com/{get_settings().microsoft_tenant}/oauth2/v2.0"

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.microsoft_client_id and s.microsoft_client_secret)

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        return f"{self._base()}/authorize?" + urlencode({
            "client_id": get_settings().microsoft_client_id, "response_type": "code", "redirect_uri": redirect_uri,
            "response_mode": "query", "scope": " ".join(self.scopes), "state": state, "prompt": "select_account"})

    def _token(self, data: dict) -> TokenSet:
        s = get_settings()
        r = httpx.post(f"{self._base()}/token", data={**data, "client_id": s.microsoft_client_id,
                                                      "client_secret": s.microsoft_client_secret,
                                                      "scope": " ".join(self.scopes)}, timeout=20)
        if r.status_code in (400, 401) and ("invalid_grant" in r.text or "AADSTS700082" in r.text):
            raise MailboxAuthError("Microsoft refresh token expired or revoked")
        _check(r)
        j = r.json()
        return TokenSet(j["access_token"], j.get("refresh_token"),
                        datetime.now(UTC) + timedelta(seconds=int(j.get("expires_in", 3600))),
                        j.get("scope", "").split())

    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet:
        return self._token({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri})

    def refresh(self, refresh_token: str) -> TokenSet:
        return self._token({"refresh_token": refresh_token, "grant_type": "refresh_token"})

    def account_identity(self, access_token: str) -> tuple[str, str | None]:
        r = httpx.get(f"{GRAPH}/me", params={"$select": "mail,userPrincipalName,displayName"},
                      headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
        _check(r)
        j = r.json()
        return (j.get("mail") or j.get("userPrincipalName")).lower(), j.get("displayName")

    def create_draft(self, access_token, *, to, subject, body, from_email, idempotency_key) -> CreatedDraft:
        payload = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
            "singleValueExtendedProperties": [{"id": KEY_PROP, "value": idempotency_key}],
        }
        # POST /me/messages creates the message in the Drafts folder; it is NOT sent.
        r = httpx.post(f"{GRAPH}/me/messages", json=payload, headers={"Authorization": f"Bearer {access_token}"},
                       timeout=30)
        _check(r)
        j = r.json()
        return CreatedDraft(draft_id=j["id"], message_id=j["id"], thread_id=j.get("conversationId"),
                            internet_message_id=j.get("internetMessageId"))

    def find_draft_by_key(self, access_token, idempotency_key) -> CreatedDraft | None:
        flt = f"singleValueExtendedProperties/Any(ep: ep/id eq '{KEY_PROP}' and ep/value eq '{idempotency_key}')"
        r = httpx.get(f"{GRAPH}/me/mailFolders/drafts/messages", params={"$filter": flt, "$select": "id,conversationId,internetMessageId"},
                      headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
        _check(r)
        vals = r.json().get("value", [])
        if not vals:
            return None
        j = vals[0]
        return CreatedDraft(draft_id=j["id"], message_id=j["id"], thread_id=j.get("conversationId"),
                            internet_message_id=j.get("internetMessageId"))

    def thread_messages(self, access_token, thread_id, my_email) -> list[ThreadMessage]:
        r = httpx.get(f"{GRAPH}/me/messages", params={
            "$filter": f"conversationId eq '{thread_id}'", "$top": "50",
            "$select": "id,from,toRecipients,subject,bodyPreview,receivedDateTime,sentDateTime,isDraft,internetMessageId"},
            headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
        _check(r)
        out = []
        for m in r.json().get("value", []):
            frm = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "")
            to = [((x.get("emailAddress") or {}).get("address") or "") for x in m.get("toRecipients", [])]
            out.append(ThreadMessage(
                message_id=m["id"], from_email=frm.lower() or None, to_email=(to[0].lower() if to else None),
                subject=m.get("subject"), snippet=m.get("bodyPreview"),
                date=_dt(m.get("receivedDateTime") or m.get("sentDateTime")), is_draft=bool(m.get("isDraft")),
                is_sent_by_me=(frm.lower() == my_email.lower()), internet_message_id=m.get("internetMessageId")))
        return out
