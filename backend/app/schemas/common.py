from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Msg(BaseModel):
    ok: bool = True
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------ auth & users
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field("", max_length=200)
    password: str = Field(min_length=10, max_length=256)
    role: str = Field("viewer", pattern="^(admin|operator|viewer)$")


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=200)
    role: str | None = Field(None, pattern="^(admin|operator|viewer)$")
    is_active: bool | None = None
    password: str | None = Field(None, min_length=10, max_length=256)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)


def _strip(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


class StrippedModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip_strings(cls, v):
        return _strip(v)
