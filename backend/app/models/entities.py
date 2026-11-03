"""All ORM models. Kept in one module so relationships resolve without import cycles."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


def _enum(e: type[enum.Enum], name: str):
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x], native_enum=False, length=40)


# --------------------------------------------------------------------------------------------- enums
class Role(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"  # can research, edit and approve drafts
    VIEWER = "viewer"


class LeadStatus(str, enum.Enum):
    NEW = "NEW"
    RESEARCHING = "RESEARCHING"
    RESEARCHED = "RESEARCHED"
    QUALIFIED = "QUALIFIED"
    DRAFT_GENERATED = "DRAFT_GENERATED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EMAIL_DRAFT_CREATED = "EMAIL_DRAFT_CREATED"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    INTERESTED = "INTERESTED"
    MEETING_REQUESTED = "MEETING_REQUESTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    DISQUALIFIED = "DISQUALIFIED"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"


class Service(str, enum.Enum):
    WEBSITE = "website"
    COMPANY_BRAIN = "company_brain"
    NONE = "none"


class EmailStatus(str, enum.Enum):
    NONE = "none"  # no email known
    UNVERIFIED = "unverified"  # supplied/imported, not checked
    PUBLISHED = "published"  # found verbatim on an official public page (still not mailbox-verified)
    DOMAIN_VALID = "domain_valid"  # syntax OK + domain has MX records (mailbox not verified)
    INVALID = "invalid"  # syntax or domain check failed
    VERIFIED = "verified"  # ONLY set by a mailbox verification provider


class DraftStatus(str, enum.Enum):
    GENERATING = "generating"
    NEEDS_REVIEW = "needs_review"  # failed quality threshold → manual research / regeneration
    PENDING_APPROVAL = "pending_approval"
    SAVED_FOR_LATER = "saved_for_later"
    APPROVED = "approved"
    EMAIL_DRAFT_CREATED = "email_draft_created"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    BLOCKED = "blocked"  # suppression / DNC


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class EvidenceCategory(str, enum.Enum):
    VERIFIED_FACT = "verified_fact"
    DIRECT_OBSERVATION = "direct_observation"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------------------------- users
class User(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), default=Role.VIEWER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # bump to revoke sessions
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("uq_users_email_lower", text("lower(email)"), unique=True),)


class Setting(IdMixin, TimestampMixin, Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # names of fields inside `value` that hold Fernet-encrypted strings
    secret_fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# ------------------------------------------------------------------------------------------ campaigns
class Campaign(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "campaigns"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_service: Mapped[str] = mapped_column(String(40), default="any")  # any|website|company_brain
    industries: Mapped[list] = mapped_column(JSONB, default=list)
    geographies: Mapped[list] = mapped_column(JSONB, default=list)  # e.g. ["United Kingdom","Germany"]
    company_sizes: Mapped[list] = mapped_column(JSONB, default=list)  # e.g. ["11-50","51-200"]
    target_roles: Mapped[list] = mapped_column(JSONB, default=list)
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    query_templates: Mapped[list] = mapped_column(JSONB, default=list)  # strings with {industry} {geo}...
    signal_focus: Mapped[list] = mapped_column(JSONB, default=list)  # funding|hiring|launch|expansion...
    sources: Mapped[list] = mapped_column(JSONB, default=list)  # provider keys to use
    rss_feeds: Mapped[list] = mapped_column(JSONB, default=list)
    daily_company_limit: Mapped[int] = mapped_column(Integer, default=25)
    daily_query_limit: Mapped[int] = mapped_column(Integer, default=20)
    auto_research: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    companies: Mapped[list[Company]] = relationship(back_populates="campaign")


class SearchQuery(IdMixin, TimestampMixin, Base):
    __tablename__ = "search_queries"
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("automation_jobs.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual|scheduled
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|ok|error|limited
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    new_companies: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    results: Mapped[list] = mapped_column(JSONB, default=list)  # compact raw results for audit
    __table_args__ = (Index("ix_search_queries_created", "created_at"),)


# ---------------------------------------------------------------------------------------- companies
class Company(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    domain_normalized: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(100))
    size_range: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LeadStatus] = mapped_column(
        _enum(LeadStatus, "lead_status"), default=LeadStatus.NEW, nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    website_score: Mapped[int | None] = mapped_column(Integer)
    brain_score: Mapped[int | None] = mapped_column(Integer)
    recommended_service: Mapped[str | None] = mapped_column(String(40))
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)  # flexible attributes (from sources)
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_signals_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_contacts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disqualified_reason: Mapped[str | None] = mapped_column(Text)

    campaign: Mapped[Campaign | None] = relationship(back_populates="companies")
    contacts: Mapped[list[Contact]] = relationship(back_populates="company")
    sources: Mapped[list[LeadSource]] = relationship(back_populates="company")
    signals: Mapped[list[BuyingSignal]] = relationship(back_populates="company")

    __table_args__ = (
        Index(
            "uq_companies_domain_normalized",
            "domain_normalized",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND domain_normalized IS NOT NULL"),
        ),
        Index("ix_companies_name_lower", text("lower(name)")),
        Index("ix_companies_created", "created_at"),
    )


class LeadSource(IdMixin, TimestampMixin, Base):
    __tablename__ = "lead_sources"
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    search_query_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("search_queries.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="search")
    source_url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)

    company: Mapped[Company | None] = relationship(back_populates="sources")


class Contact(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "contacts"
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(200))
    seniority_rank: Mapped[int] = mapped_column(Integer, default=99)  # lower = more senior/relevant
    email: Mapped[str | None] = mapped_column(String(320))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    email_status: Mapped[EmailStatus] = mapped_column(
        _enum(EmailStatus, "email_status"), default=EmailStatus.NONE, nullable=False
    )
    email_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_check_detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    profile_url: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(40), default="website")
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="active")  # active|do_not_contact
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    company: Mapped[Company | None] = relationship(back_populates="contacts")

    __table_args__ = (
        Index(
            "uq_contacts_email_normalized",
            "email_normalized",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND email_normalized IS NOT NULL"),
        ),
        Index("ix_contacts_name_company", "company_id", text("lower(full_name)")),
    )


# ----------------------------------------------------------------------------------------- research
class ResearchReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "research_reports"
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("automation_jobs.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="complete")  # complete|partial|blocked|failed
    summary: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[list] = mapped_column(JSONB, default=list)  # [{id,url,kind,title,meta,headings,...}]
    audit: Mapped[dict] = mapped_column(JSONB, default=dict)  # measurable checks (deterministic)
    analysis: Mapped[dict] = mapped_column(JSONB, default=dict)  # AI analysis (validated)
    observations: Mapped[list] = mapped_column(JSONB, default=list)  # [{category, area, text, evidence}]
    evidence: Mapped[list] = mapped_column(JSONB, default=list)  # [{id,url,quote,kind}]
    business_info: Mapped[dict] = mapped_column(JSONB, default=dict)
    robots: Mapped[dict] = mapped_column(JSONB, default=dict)
    injection_flags: Mapped[list] = mapped_column(JSONB, default=list)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BuyingSignal(IdMixin, TimestampMixin, Base):
    __tablename__ = "buying_signals"
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    freshness: Mapped[str] = mapped_column(String(20), default="unknown")  # fresh|recent|stale|unknown
    method: Mapped[str] = mapped_column(String(20), default="rule")  # rule|llm
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    company: Mapped[Company] = relationship(back_populates="signals")
    __table_args__ = (UniqueConstraint("company_id", "source_url", "signal_type", name="uq_signal_source"),)


class Opportunity(IdMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    website_score: Mapped[int | None] = mapped_column(Integer)
    website_confidence: Mapped[float | None] = mapped_column(Float)
    website_explanation: Mapped[str | None] = mapped_column(Text)
    brain_score: Mapped[int | None] = mapped_column(Integer)
    brain_confidence: Mapped[float | None] = mapped_column(Float)
    brain_explanation: Mapped[str | None] = mapped_column(Text)
    recommended_service: Mapped[str] = mapped_column(String(40), default="none")
    recommendation_reason: Mapped[str | None] = mapped_column(Text)
    sales_angle: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    method: Mapped[str] = mapped_column(String(20), default="llm")
    research_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_reports.id", ondelete="SET NULL")
    )
    stage: Mapped[str] = mapped_column(String(40), default="open")  # open|won|lost


class LeadScore(IdMixin, TimestampMixin, Base):
    __tablename__ = "lead_scores"
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    service: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    factors: Mapped[list] = mapped_column(JSONB, default=list)
    explanation: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    sales_angle: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(20), default="llm")
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_runs.id", ondelete="SET NULL"))


# ----------------------------------------------------------------------------------------- outreach
class OutreachDraft(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "outreach_drafts"
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    service: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        _enum(DraftStatus, "draft_status"), default=DraftStatus.PENDING_APPROVAL, nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    opening_line: Mapped[str | None] = mapped_column(Text)
    linkedin_connection_note: Mapped[str | None] = mapped_column(Text)
    linkedin_message: Mapped[str | None] = mapped_column(Text)
    recommended_offer: Mapped[str | None] = mapped_column(Text)
    personalisation_explanation: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    quality_score: Mapped[int | None] = mapped_column(Integer)
    quality_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    regeneration_count: Mapped[int] = mapped_column(Integer, default=0)
    regeneration_notes: Mapped[str | None] = mapped_column(Text)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    original: Mapped[dict] = mapped_column(JSONB, default=dict)  # AI original before human edits
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    ai_run_ids: Mapped[list] = mapped_column(JSONB, default=list)

    company: Mapped[Company] = relationship()
    contact: Mapped[Contact | None] = relationship()


class Approval(IdMixin, TimestampMixin, Base):
    __tablename__ = "approvals"
    outreach_draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_drafts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    # approve|edit|reject|save_for_later|request_regeneration|do_not_contact
    comment: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict] = mapped_column(JSONB, default=dict)
    draft_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)


# -------------------------------------------------------------------------------------------- email
class EmailAccount(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "email_accounts"
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # gmail|outlook
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="connected")  # connected|expired|revoked|error
    scopes: Mapped[list] = mapped_column(JSONB, default=list)
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    connected_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    __table_args__ = (UniqueConstraint("provider", "email", name="uq_email_account_provider_email"),)


class EmailDraft(IdMixin, TimestampMixin, Base):
    __tablename__ = "email_drafts"
    outreach_draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_drafts.id", ondelete="CASCADE"), index=True
    )
    email_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_accounts.id", ondelete="CASCADE"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|created|failed|sent_by_user
    external_draft_id: Mapped[str | None] = mapped_column(String(300))
    external_message_id: Mapped[str | None] = mapped_column(String(500))
    external_thread_id: Mapped[str | None] = mapped_column(String(500))  # gmail threadId / outlook conversationId
    internet_message_id: Mapped[str | None] = mapped_column(String(500))
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("outreach_draft_id", "email_account_id", name="uq_email_draft_per_account"),
    )


class Interaction(IdMixin, TimestampMixin, Base):
    __tablename__ = "interactions"
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    email_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_accounts.id", ondelete="SET NULL")
    )
    email_draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_drafts.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(30), default="email")  # email|linkedin|call|meeting|note
    direction: Mapped[str] = mapped_column(String(10), default="inbound")  # inbound|outbound
    external_message_id: Mapped[str | None] = mapped_column(String(500))
    external_thread_id: Mapped[str | None] = mapped_column(String(500))
    from_email: Mapped[str | None] = mapped_column(String(320))
    to_email: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    classification: Mapped[str | None] = mapped_column(String(40))
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classification_detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    suggested_reply: Mapped[str | None] = mapped_column(Text)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    handled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        Index(
            "uq_interaction_external",
            "email_account_id",
            "external_message_id",
            unique=True,
            postgresql_where=text("external_message_id IS NOT NULL"),
        ),
    )


class Task(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|done|cancelled
    kind: Mapped[str] = mapped_column(String(30), default="follow_up")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Note(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "notes"
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Suppression(IdMixin, TimestampMixin, Base):
    """Never hard-deleted by retention jobs. `kind` = email|domain."""

    __tablename__ = "suppression_list"
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[str] = mapped_column(String(320), nullable=False)
    reason: Mapped[str] = mapped_column(String(60), default="manual")  # opt_out|unsubscribe|manual|bounce|dnc
    source: Mapped[str | None] = mapped_column(Text)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_suppression_kind_value"),)


# --------------------------------------------------------------------------------------- automation
class AutomationJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "automation_jobs"
    workflow: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual|scheduled|chained|api
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.QUEUED, nullable=False, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    log: Mapped[list] = mapped_column(JSONB, default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    celery_task_id: Mapped[str | None] = mapped_column(String(200))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("automation_jobs.id", ondelete="SET NULL"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    __table_args__ = (Index("ix_automation_jobs_created", "created_at"),)


class WorkflowSchedule(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_schedules"
    workflow: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    cron: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_size: Mapped[int] = mapped_column(Integer, default=10)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_runs"
    agent: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok|error|invalid_output|budget_blocked
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("automation_jobs.id", ondelete="SET NULL"))
    prompt_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    request_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("ix_ai_runs_created", "created_at"),)


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_type: Mapped[str] = mapped_column(String(20), default="user")  # user|system|agent
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


# ------------------------------------------------------------------------------- company brain/kb
class KnowledgeItem(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "knowledge_items"
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # service|pricing|portfolio|case_study|testimonial|positioning|proposal|messaging|other
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(1000))
    service: Mapped[str | None] = mapped_column(String(40))  # website|company_brain|both
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    source: Mapped[str] = mapped_column(String(40), default="manual")  # manual|notion|slack|teams|...
    source_ref: Mapped[str | None] = mapped_column(String(500))
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="SET NULL")
    )
    approved_for_outreach: Mapped[bool] = mapped_column(Boolean, default=False)
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)


class IntegrationConnection(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "integration_connections"
    provider: Mapped[str] = mapped_column(String(40), nullable=False)  # notion|slack|teams|gmail|outlook
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="not_configured")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # non-secret config
    credentials_enc: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class PageCache(IdMixin, TimestampMixin, Base):
    __tablename__ = "page_cache"
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    status_code: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(200))
    final_url: Mapped[str | None] = mapped_column(String(2000))
    html: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rendered: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(200))
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    headers: Mapped[dict] = mapped_column(JSONB, default=dict)
