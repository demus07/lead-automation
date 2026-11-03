"""Mailbox provider interface. Deliberately has NO send method: the application can only create
unsent drafts and read message metadata. Sending happens manually in the user's mail client."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class MailboxAuthError(Exception):
    """Token expired/revoked — account needs reconnecting."""


class MailboxError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str] = field(default_factory=list)


@dataclass
class CreatedDraft:
    draft_id: str
    message_id: str | None
    thread_id: str | None
    internet_message_id: str | None = None


@dataclass
class ThreadMessage:
    message_id: str
    from_email: str | None
    to_email: str | None
    subject: str | None
    snippet: str | None
    date: datetime | None
    is_draft: bool
    is_sent_by_me: bool
    internet_message_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class MailboxProvider(ABC):
    key: str = ""
    scopes: list[str] = []

    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    def authorize_url(self, state: str, redirect_uri: str) -> str: ...

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet: ...

    @abstractmethod
    def refresh(self, refresh_token: str) -> TokenSet: ...

    @abstractmethod
    def account_identity(self, access_token: str) -> tuple[str, str | None]:
        """Returns (email, display_name)."""

    @abstractmethod
    def create_draft(self, access_token: str, *, to: str, subject: str, body: str, from_email: str,
                     idempotency_key: str) -> CreatedDraft: ...

    @abstractmethod
    def find_draft_by_key(self, access_token: str, idempotency_key: str) -> CreatedDraft | None:
        """Recover a draft created by a previous attempt that crashed before we stored its id."""

    @abstractmethod
    def thread_messages(self, access_token: str, thread_id: str, my_email: str) -> list[ThreadMessage]: ...
