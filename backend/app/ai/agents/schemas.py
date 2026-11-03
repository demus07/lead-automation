"""Input/output schemas for every agent. Outputs are validated by Pydantic and then cross-checked
against stored evidence by deterministic code before anything is persisted."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["verified_fact", "direct_observation", "hypothesis", "unknown"]
Area = Literal[
    "brand_positioning", "value_proposition", "messaging", "visual_consistency", "navigation",
    "information_architecture", "product_presentation", "user_experience", "conversion_paths",
    "mobile_usability", "accessibility", "content_quality", "business",
]


# ---------------------------------------------------------------- Discovery Agent
class ExtractedCompany(BaseModel):
    name: str = Field(max_length=200)
    website: str | None = Field(None, max_length=300, description="Only if explicitly present in the text")
    signal_type: Literal["funding", "product_launch", "expansion", "hiring", "executive_appointment",
                         "acquisition", "rebrand", "digital_transformation", "growth", "other"] | None = None
    evidence_quote: str = Field(max_length=400, description="Exact substring of the result that names the company")
    result_id: str


class DiscoveryOutput(BaseModel):
    companies: list[ExtractedCompany] = Field(default_factory=list, max_length=30)


# ---------------------------------------------------------------- Contact Research Agent
class ExtractedPerson(BaseModel):
    full_name: str = Field(max_length=120)
    job_title: str | None = Field(None, max_length=200)
    quote: str = Field(max_length=300, description="Exact substring of the page containing name and title")


class ContactResearchOutput(BaseModel):
    people: list[ExtractedPerson] = Field(default_factory=list, max_length=40)


# ---------------------------------------------------------------- Website Research Agent
class Observation(BaseModel):
    area: Area
    category: Category
    text: str = Field(max_length=600)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    quote: str | None = Field(None, max_length=300, description="Exact substring of a cited page, if quoting")


class BusinessInfo(BaseModel):
    offerings: list[str] = Field(default_factory=list, max_length=12)
    target_customers: str | None = Field(None, max_length=400)
    business_model: str | None = Field(None, max_length=300)
    locations: list[str] = Field(default_factory=list, max_length=12)
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class WebsiteResearchOutput(BaseModel):
    summary: str = Field(max_length=1200, description="Neutral 2-4 sentence summary of what the company does")
    value_proposition: str | None = Field(None, max_length=400)
    observations: list[Observation] = Field(default_factory=list, max_length=30)
    business_info: BusinessInfo = Field(default_factory=BusinessInfo)
    possible_prompt_injection: bool = False


# ---------------------------------------------------------------- Business Signal Agent
class SignalClassification(BaseModel):
    item_id: str
    signal_type: Literal["funding", "product_launch", "expansion", "hiring", "executive_appointment",
                         "acquisition", "rebrand", "digital_transformation", "growth", "partnership", "none"]
    about_this_company: bool
    description: str = Field(max_length=300)
    confidence: float = Field(ge=0, le=1)


class BusinessSignalOutput(BaseModel):
    items: list[SignalClassification] = Field(default_factory=list, max_length=40)


# ---------------------------------------------------------------- Opportunity Scoring Agent
class FactorRating(BaseModel):
    factor: str
    rating: int | None = Field(None, ge=0, le=5, description="0-5 strength of opportunity; null = unknown")
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    rationale: str = Field(max_length=400)


class ServiceAssessment(BaseModel):
    factors: list[FactorRating] = Field(max_length=12)
    explanation: str = Field(max_length=800)
    sales_angle: str | None = Field(None, max_length=400)


class ScoringOutput(BaseModel):
    website: ServiceAssessment
    company_brain: ServiceAssessment


# ---------------------------------------------------------------- Outreach Generation Agent
class Claim(BaseModel):
    text: str = Field(max_length=300, description="A factual statement about the prospect used in the message")
    evidence_ids: list[str] = Field(default_factory=list, max_length=4)


class OutreachOutput(BaseModel):
    subject: str = Field(max_length=120)
    opening_line: str = Field(max_length=300)
    body: str = Field(max_length=2000, description="Full email body including greeting and sign-off")
    linkedin_connection_note: str = Field(max_length=300)
    linkedin_message: str = Field(max_length=1200)
    recommended_offer: str = Field(max_length=300)
    personalisation_explanation: str = Field(max_length=600)
    claims: list[Claim] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)


# ---------------------------------------------------------------- Outreach Quality Agent
class QualityIssue(BaseModel):
    type: Literal["unsupported_claim", "invented_fact", "misleading", "wrong_service", "generic", "tone",
                  "sensitive_info", "cta", "name_error", "length", "other"]
    severity: Literal["low", "medium", "high"]
    text: str = Field(max_length=400)


class QualityOutput(BaseModel):
    issues: list[QualityIssue] = Field(default_factory=list, max_length=20)
    accuracy: int = Field(ge=0, le=100)
    relevance: int = Field(ge=0, le=100)
    personalisation: int = Field(ge=0, le=100)
    tone: int = Field(ge=0, le=100)
    call_to_action: int = Field(ge=0, le=100)
    summary: str = Field(max_length=600)


# ---------------------------------------------------------------- Reply Classification Agent
ReplyLabel = Literal["interested", "meeting_requested", "needs_information", "objection", "not_interested",
                     "unsubscribe", "out_of_office", "automatic_reply", "unknown"]


class ReplyOutput(BaseModel):
    label: ReplyLabel
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(max_length=400)
    opt_out_requested: bool
    suggested_reply: str | None = Field(None, max_length=1500)
    suggested_action: str = Field(max_length=300)


# ---------------------------------------------------------------- Main Orchestrator Agent
class OrchestratorOutput(BaseModel):
    lead_summary: str = Field(max_length=900, description="Brief for the human approver")
    next_action: Literal["research_more", "find_contacts", "qualify", "draft", "disqualify", "wait"]
    reason: str = Field(max_length=400)
    open_questions: list[str] = Field(default_factory=list, max_length=6)
