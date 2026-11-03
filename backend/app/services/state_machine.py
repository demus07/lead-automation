"""Validated lead-status transitions. Deterministic — never decided by an LLM."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Company, LeadStatus, User
from app.services.audit import audit

S = LeadStatus

TERMINAL = {S.DO_NOT_CONTACT}

TRANSITIONS: dict[LeadStatus, set[LeadStatus]] = {
    S.NEW: {S.RESEARCHING, S.RESEARCHED},
    S.RESEARCHING: {S.RESEARCHED, S.NEW},  # NEW = research failed, retry later
    S.RESEARCHED: {S.RESEARCHING, S.QUALIFIED},
    S.QUALIFIED: {S.DRAFT_GENERATED, S.RESEARCHING, S.RESEARCHED},
    S.DRAFT_GENERATED: {S.PENDING_APPROVAL, S.QUALIFIED},
    S.PENDING_APPROVAL: {S.APPROVED, S.QUALIFIED, S.DRAFT_GENERATED},
    S.APPROVED: {S.EMAIL_DRAFT_CREATED, S.PENDING_APPROVAL},
    S.EMAIL_DRAFT_CREATED: {S.CONTACTED, S.APPROVED, S.PENDING_APPROVAL},
    S.CONTACTED: {S.REPLIED, S.INTERESTED, S.MEETING_REQUESTED, S.NOT_INTERESTED, S.PENDING_APPROVAL},
    S.REPLIED: {S.INTERESTED, S.MEETING_REQUESTED, S.NOT_INTERESTED, S.PENDING_APPROVAL},
    S.INTERESTED: {S.MEETING_REQUESTED, S.NOT_INTERESTED, S.REPLIED},
    S.MEETING_REQUESTED: {S.INTERESTED, S.NOT_INTERESTED},
    S.NOT_INTERESTED: {S.INTERESTED, S.REPLIED},
    S.DISQUALIFIED: {S.NEW, S.RESEARCHING},
    S.DO_NOT_CONTACT: set(),
}
# Any non-terminal state may move to DISQUALIFIED or DO_NOT_CONTACT.
for _s in list(TRANSITIONS):
    if _s not in TERMINAL:
        TRANSITIONS[_s] |= {S.DISQUALIFIED, S.DO_NOT_CONTACT}
    TRANSITIONS[_s].discard(_s)

# States from which outreach may still be generated.
OUTREACH_BLOCKED = {S.DO_NOT_CONTACT, S.DISQUALIFIED, S.NOT_INTERESTED}


class InvalidTransition(ValueError):
    pass


def can_transition(current: LeadStatus, target: LeadStatus) -> bool:
    return target in TRANSITIONS.get(current, set())


def allowed_targets(current: LeadStatus) -> list[str]:
    return sorted(t.value for t in TRANSITIONS.get(current, set()))


def transition(
    db: Session,
    company: Company,
    target: LeadStatus,
    *,
    actor: User | None = None,
    reason: str | None = None,
    force_forward: bool = False,
) -> bool:
    """Move a company to `target`. Returns True if changed.

    ``force_forward`` lets system workflows walk a multi-step path (e.g. NEW→RESEARCHING→RESEARCHED)
    only along valid edges; it never allows leaving DO_NOT_CONTACT.
    """
    current = company.status
    if current == target:
        return False
    if current in TERMINAL:
        raise InvalidTransition(f"{current.value} is terminal")
    if not can_transition(current, target):
        raise InvalidTransition(f"Cannot move from {current.value} to {target.value}")
    company.status = target
    audit(
        db,
        "lead.status_changed",
        actor=actor,
        entity_type="company",
        entity_id=company.id,
        detail={"from": current.value, "to": target.value, "reason": reason},
    )
    return True


def try_transition(db: Session, company: Company, target: LeadStatus, **kw) -> bool:
    """Transition if valid; otherwise no-op (used by workflows advancing opportunistically)."""
    try:
        return transition(db, company, target, **kw)
    except InvalidTransition:
        return False
