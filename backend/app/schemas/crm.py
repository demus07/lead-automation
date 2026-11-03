from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class CompanyOut(ORM):
    id: uuid.UUID
    name: str
    domain: str | None
    website: str | None
    industry: str | None
    location: str | None
    country: str | None
    size_range: str | None
    description: str | None
    status: str
    campaign_id: uuid.UUID | None
    website_score: int | None
    brain_score: int | None
    recommended_service: str | None
    tags: list[str]
    last_researched_at: datetime | None
    last_scored_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    website: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, max_length=200)
    location: str | None = Field(None, max_length=300)
    country: str | None = Field(None, max_length=100)
    size_range: str | None = Field(None, max_length=40)
    description: str | None = Field(None, max_length=4000)
    campaign_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)


class CompanyPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    industry: str | None = Field(None, max_length=200)
    location: str | None = Field(None, max_length=300)
    country: str | None = Field(None, max_length=100)
    size_range: str | None = Field(None, max_length=40)
    description: str | None = Field(None, max_length=4000)
    campaign_id: uuid.UUID | None = None
    tags: list[str] | None = None
    owner_id: uuid.UUID | None = None


class StatusChange(BaseModel):
    status: str
    reason: str | None = Field(None, max_length=1000)


class BulkAction(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(status|tag|untag|delete|research|qualify|draft|campaign)$")
    value: Any = None


class ContactOut(ORM):
    id: uuid.UUID
    company_id: uuid.UUID | None
    full_name: str
    first_name: str | None
    last_name: str | None
    job_title: str | None
    seniority_rank: int
    email: str | None
    email_status: str
    email_checked_at: datetime | None
    email_check_detail: dict
    profile_url: str | None
    source_url: str | None
    source_type: str
    discovered_at: datetime | None
    confidence: float
    is_primary: bool
    status: str
    created_at: datetime


class ContactWithCompany(ContactOut):
    company_name: str | None = None
    company_domain: str | None = None


class ContactIn(BaseModel):
    company_id: uuid.UUID
    full_name: str = Field(min_length=1, max_length=200)
    job_title: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=320)
    profile_url: str | None = Field(None, max_length=500)
    source_url: str | None = Field(None, max_length=1000)


class ContactPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    job_title: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=320)
    profile_url: str | None = Field(None, max_length=500)
    is_primary: bool | None = None


class LeadSourceOut(ORM):
    id: uuid.UUID
    provider: str
    source_type: str
    source_url: str | None
    title: str | None
    snippet: str | None
    created_at: datetime


class SignalOut(ORM):
    id: uuid.UUID
    company_id: uuid.UUID
    signal_type: str
    description: str
    source_url: str
    source_name: str | None
    published_at: datetime | None
    discovered_at: datetime
    evidence: str | None
    confidence: float
    freshness: str
    method: str


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    contact_id: uuid.UUID | None = None


class NoteOut(ORM):
    id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    author_id: uuid.UUID | None
    body: str
    created_at: datetime


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None
    kind: str = Field("follow_up", max_length=30)


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None
    status: str | None = Field(None, pattern="^(open|done|cancelled)$")


class TaskOut(ORM):
    id: uuid.UUID
    title: str
    description: str | None
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    due_at: datetime | None
    status: str
    kind: str
    completed_at: datetime | None
    created_at: datetime
    company_name: str | None = None
