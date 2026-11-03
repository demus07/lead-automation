from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin, require_viewer
from app.models import User
from app.services import settings_service as ss
from app.services.audit import audit

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Sections operators may read but only admins may change.
SECTIONS = list(ss.DEFAULTS)


@router.get("")
def all_settings(db: Session = Depends(get_db), _: User = Depends(require_viewer)) -> dict[str, Any]:
    return {k: ss.public_section(db, k) for k in SECTIONS}


@router.get("/{section}")
def get_settings_section(section: str, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    if section not in SECTIONS:
        raise HTTPException(404, "Unknown settings section")
    return ss.public_section(db, section)


@router.put("/{section}")
def update_settings_section(
    section: str,
    patch: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if section not in SECTIONS:
        raise HTTPException(404, "Unknown settings section")
    _validate(section, patch)
    result = ss.update_section(db, section, patch, admin)
    changed = sorted(k for k in patch if k in ss.DEFAULTS[section])
    audit(db, "settings.updated", actor=admin, entity_type="settings", entity_id=None,
          detail={"section": section, "fields": changed})
    db.commit()
    return result


def _validate(section: str, patch: dict[str, Any]) -> None:
    def num(key: str, lo: float, hi: float):
        if key in patch:
            try:
                v = float(patch[key])
            except (TypeError, ValueError):
                raise HTTPException(422, f"{key} must be a number") from None
            if not lo <= v <= hi:
                raise HTTPException(422, f"{key} must be between {lo} and {hi}")

    if section == "llm":
        if "provider" in patch and patch["provider"] not in ("none", "openai_compatible", "anthropic"):
            raise HTTPException(422, "Unknown LLM provider")
        if "base_url" in patch and patch["base_url"] and not str(patch["base_url"]).startswith(("http://", "https://")):
            raise HTTPException(422, "base_url must be an http(s) URL")
        num("temperature", 0, 2)
        num("daily_budget_usd", 0, 10_000)
        num("max_calls_per_company", 1, 200)
        num("max_output_tokens", 100, 32_000)
    if section == "discovery":
        if "web_search_provider" in patch and patch["web_search_provider"] not in (
            "none", "brave", "tavily", "serpapi", "searxng"):
            raise HTTPException(422, "Unknown search provider")
        num("daily_search_quota", 0, 100_000)
    if section == "quality":
        num("threshold", 0, 100)
        num("max_regenerations", 0, 10)
    if section == "scoring":
        num("qualification_threshold", 0, 100)
        num("service_margin", 0, 100)
    for k, v in patch.items():
        if isinstance(v, str) and len(v) > 20_000:
            raise HTTPException(422, f"{k} is too long")
