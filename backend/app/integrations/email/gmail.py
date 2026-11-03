"""Gmail via the official Gmail REST API (OAuth2).

Scopes: gmail.compose (create drafts) + gmail.metadata (read headers/snippets of thread messages
for reply detection). The code never calls any Gmail send endpoint."""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
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

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
KEY_HEADER = "X-AGE-Draft-Key"


def _check(r: httpx.Response) -> None:
    if r.status_code == 401:
        raise MailboxAuthError("Gmail access token rejected")
    if r.status_code == 403 and "insufficient" in r.text.lower():
        raise MailboxAuthError("Gmail permission missing — reconnect the account")
    if r.status_code == 429 or r.status_code >= 500:
        raise MailboxError(f"Gmail HTTP {r.status_code}", retryable=True)
    if r.status_code >= 400:
        raise MailboxError(f"Gmail HTTP {r.status_code}: {r.text[:300]}", retryable=False)


class GmailProvider(MailboxProvider):
    key = "gmail"
    scopes = ["openid", "email", "https://www.googleapis.com/auth/gmail.compose",
              "https://www.googleapis.com/auth/gmail.metadata"]

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.google_client_id and s.google_client_secret)

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": get_settings().google_client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(self.scopes), "access_type": "offline", "prompt": "consent",
            "include_granted_scopes": "false", "state": state})

    def _token(self, data: dict) -> TokenSet:
        s = get_settings()
        r = httpx.post(TOKEN_URL, data={**data, "client_id": s.google_client_id,
                                        "client_secret": s.google_client_secret}, timeout=20)
        if r.status_code == 400 and "invalid_grant" in r.text:
            raise MailboxAuthError("Google refresh token expired or revoked")
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
        r = httpx.get(f"{API}/profile", headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
        _check(r)
        return r.json()["emailAddress"], None

    def create_draft(self, access_token, *, to, subject, body, from_email, idempotency_key) -> CreatedDraft:
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = from_email
        msg["Subject"] = subject
        msg[KEY_HEADER] = idempotency_key
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = httpx.post(f"{API}/drafts", json={"message": {"raw": raw}},
                       headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
        _check(r)
        j = r.json()
        m = j.get("message", {})
        return CreatedDraft(draft_id=j["id"], message_id=m.get("id"), thread_id=m.get("threadId"))

    def find_draft_by_key(self, access_token, idempotency_key) -> CreatedDraft | None:
        h = {"Authorization": f"Bearer {access_token}"}
        r = httpx.get(f"{API}/drafts", params={"maxResults": 50}, headers=h, timeout=20)
        _check(r)
        for d in r.json().get("drafts", []):
            g = httpx.get(f"{API}/drafts/{d['id']}", params={"format": "metadata"}, headers=h, timeout=20)
            if g.status_code != 200:
                continue
            m = g.json().get("message", {})
            headers = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
            if headers.get(KEY_HEADER.lower()) == idempotency_key:
                return CreatedDraft(draft_id=d["id"], message_id=m.get("id"), thread_id=m.get("threadId"))
        return None

    def thread_messages(self, access_token, thread_id, my_email) -> list[ThreadMessage]:
        r = httpx.get(f"{API}/threads/{thread_id}",
                      params=[("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "To"),
                              ("metadataHeaders", "Subject"), ("metadataHeaders", "Date"),
                              ("metadataHeaders", "Message-ID"), ("metadataHeaders", "Auto-Submitted")],
                      headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
        if r.status_code == 404:
            return []  # draft deleted by user before sending
        _check(r)
        out = []
        for m in r.json().get("messages", []):
            headers = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
            labels = m.get("labelIds", [])
            from_email = parseaddr(headers.get("from", ""))[1].lower() or None
            date = None
            try:
                date = parsedate_to_datetime(headers["date"]) if headers.get("date") else None
            except (TypeError, ValueError):
                pass
            out.append(ThreadMessage(
                message_id=m["id"], from_email=from_email, to_email=parseaddr(headers.get("to", ""))[1].lower() or None,
                subject=headers.get("subject"), snippet=m.get("snippet"), date=date, is_draft="DRAFT" in labels,
                is_sent_by_me="SENT" in labels or from_email == my_email.lower(),
                internet_message_id=headers.get("message-id"),
                raw={"labels": labels, "auto_submitted": headers.get("auto-submitted")}))
        return out
