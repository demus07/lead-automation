"""Buying-signal persistence and deterministic freshness scoring."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BuyingSignal, Company
from app.models.base import utcnow

SIGNAL_TYPES = [
    "funding", "product_launch", "expansion", "hiring", "executive_appointment", "acquisition", "rebrand",
    "digital_transformation", "growth", "partnership", "other",
]


def freshness(published_at: datetime | None, fresh_days: int = 90, recent_days: int = 180) -> str:
    if not published_at:
        return "unknown"
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - published_at).days
    if age < 0:
        return "unknown"  # future-dated: don't trust
    if age <= fresh_days:
        return "fresh"
    if age <= recent_days:
        return "recent"
    return "stale"


def save_signal(
    db: Session,
    company: Company,
    *,
    signal_type: str,
    description: str,
    source_url: str,
    published_at: datetime | None = None,
    evidence: str | None = None,
    confidence: float = 0.5,
    source_name: str | None = None,
    method: str = "rule",
    data: dict | None = None,
    fresh_days: int = 90,
    recent_days: int = 180,
) -> tuple[BuyingSignal, bool]:
    if signal_type not in SIGNAL_TYPES:
        signal_type = "other"
    existing = db.scalar(select(BuyingSignal).where(
        BuyingSignal.company_id == company.id, BuyingSignal.source_url == source_url[:1000],
        BuyingSignal.signal_type == signal_type))
    fr = freshness(published_at, fresh_days, recent_days)
    if existing:
        existing.freshness = fr
        return existing, False
    sig = BuyingSignal(
        company_id=company.id, signal_type=signal_type, description=description[:2000],
        source_url=source_url[:1000], source_name=source_name, published_at=published_at,
        discovered_at=utcnow(), evidence=(evidence or "")[:2000] or None,
        confidence=max(0.0, min(1.0, confidence)), freshness=fr, method=method, data=data or {},
    )
    db.add(sig)
    company.last_signals_at = utcnow()
    db.flush()
    return sig, True
