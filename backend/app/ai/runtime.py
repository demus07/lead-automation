"""Agent runtime: budgets, caching, retries, structured-output validation and usage tracking.

Agents are pure functions from (system prompt, task content) → JSON validated against a Pydantic
schema. They have no tools and no DB access. Every call is recorded in ``ai_runs``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.llm.base import LLMError, LLMNotConfigured, LLMRequest
from app.ai.llm.providers import build_provider, llm_available
from app.ai.sanitize import UNTRUSTED_NOTICE
from app.models import AIRun
from app.services import settings_service

log = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"
T = TypeVar("T", bound=BaseModel)


class AgentUnavailable(Exception):
    """LLM not configured — caller should fall back to deterministic behaviour or report limited mode."""


class BudgetExceeded(Exception):
    pass


class AgentFailed(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class AgentResult(Generic[T]):
    output: T
    run_id: uuid.UUID | None
    cached: bool = False
    model: str = ""


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def ai_status(db: Session) -> dict[str, Any]:
    cfg = settings_service.get_section(db, "llm")
    spent = spend_today(db)
    return {"available": llm_available(cfg), "provider": cfg.get("provider"), "spent_today_usd": spent,
            "daily_budget_usd": float(cfg.get("daily_budget_usd", 0)),
            "budget_remaining_usd": max(0.0, float(cfg.get("daily_budget_usd", 0)) - spent)}


def spend_today(db: Session) -> float:
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return float(db.scalar(select(func.coalesce(func.sum(AIRun.cost_usd), 0)).where(AIRun.created_at >= since)) or 0)


def calls_for_company(db: Session, company_id: uuid.UUID, days: int = 1) -> int:
    since = datetime.now(UTC) - timedelta(days=days)
    return db.scalar(select(func.count()).select_from(AIRun).where(
        AIRun.company_id == company_id, AIRun.created_at >= since, AIRun.status != "cached")) or 0


def cost_usd(cfg: dict, model: str, inp: int, out: int, cached: int) -> float:
    pricing = cfg.get("pricing", {})
    p = pricing.get(model)
    if p is None:  # match by prefix (e.g. dated model ids)
        p = next((v for k, v in pricing.items() if model.startswith(k)), None)
    if not p:
        return 0.0
    cache_rate = p.get("cache_read", p["input"] * 0.1)
    return round((inp * p["input"] + out * p["output"] + cached * cache_rate) / 1_000_000, 6)


def extract_json(text: str) -> Any:
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    if not t.startswith(("{", "[")):
        start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
        if start < 0:
            raise ValueError("No JSON object in model output")
        t = t[start:]
    # tolerate trailing prose after the JSON object
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(t)
    return obj


def run_agent(
    db: Session,
    *,
    agent: str,
    system: str,
    user: str,
    schema: type[T],
    tier: str = "smart",
    company_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    cache_days: int = 7,
    max_tokens: int | None = None,
    use_cache: bool = True,
) -> AgentResult[T]:
    cfg = settings_service.get_section(db, "llm")
    if not llm_available(cfg):
        raise AgentUnavailable("No LLM provider configured (Settings → AI configuration)")
    model = cfg["model_fast"] if tier == "fast" else cfg["model_smart"]
    full_system = f"{system.strip()}\n\n{UNTRUSTED_NOTICE}\n\nRespond with a single JSON object only."
    schema_hint = json.dumps(schema.model_json_schema(), separators=(",", ":"))[:6000]
    user_msg = f"{user}\n\nReturn JSON matching this JSON Schema:\n{schema_hint}"
    phash = hashlib.sha256(f"{agent}|{model}|{full_system}|{user_msg}".encode()).hexdigest()

    # 1) Duplicate-research prevention: identical prompt recently answered → reuse.
    if use_cache:
        prev = db.scalar(select(AIRun).where(
            AIRun.prompt_hash == phash, AIRun.status == "ok",
            AIRun.created_at >= datetime.now(UTC) - timedelta(days=cache_days)).order_by(AIRun.created_at.desc()))
        if prev and prev.output:
            try:
                return AgentResult(schema.model_validate(prev.output), prev.id, cached=True, model=prev.model)
            except ValidationError:
                pass

    # 2) Budgets
    budget = float(cfg.get("daily_budget_usd", 0) or 0)
    if budget and spend_today(db) >= budget:
        _record(db, agent, cfg, model, "budget_blocked", company_id, job_id, phash, error="Daily AI budget reached")
        raise BudgetExceeded(f"Daily AI budget of ${budget:.2f} reached")
    if company_id and calls_for_company(db, company_id) >= int(cfg.get("max_calls_per_company", 12)):
        _record(db, agent, cfg, model, "budget_blocked", company_id, job_id, phash,
                error="Max AI calls per prospect reached")
        raise BudgetExceeded("Maximum AI calls for this prospect reached today")

    provider = build_provider(cfg)
    max_retries = int(cfg.get("max_retries", 2))
    attempts, tin, tout, tcached = 0, 0, 0, 0
    last_err = ""
    messages_user = user_msg
    start = time.perf_counter()
    while attempts <= max_retries:
        attempts += 1
        req = LLMRequest(
            system=full_system, user=messages_user, model=model,
            max_tokens=max_tokens or int(cfg.get("max_output_tokens", 1800)),
            temperature=None if cfg.get("provider") == "anthropic" else float(cfg.get("temperature", 0.3)),
            json_mode=bool(cfg.get("json_mode", True)),
            effort=cfg.get("effort_fast") if tier == "fast" else cfg.get("effort_smart"),
            timeout=float(cfg.get("timeout_seconds", 90)),
        )
        try:
            resp = provider.complete(req)
        except LLMNotConfigured as e:
            raise AgentUnavailable(str(e)) from e
        except LLMError as e:
            last_err = str(e)
            if e.retryable and attempts <= max_retries:
                time.sleep(min(2 ** attempts, 20))
                continue
            _record(db, agent, cfg, model, "error", company_id, job_id, phash, error=last_err, attempts=attempts,
                    tin=tin, tout=tout, tcached=tcached, latency=start)
            raise AgentFailed(last_err, retryable=e.retryable) from e
        tin += resp.input_tokens
        tout += resp.output_tokens
        tcached += resp.cached_tokens
        try:
            data = extract_json(resp.text)
            out = schema.model_validate(data)
        except (ValueError, ValidationError) as e:
            last_err = f"Invalid structured output: {str(e)[:500]}"
            # Repair attempt: tell the model what was wrong (no untrusted content is re-sent as instruction).
            messages_user = (f"{user_msg}\n\nYour previous reply was not valid for the schema. Error:\n"
                             f"{str(e)[:800]}\nReturn corrected JSON only.")
            continue
        run = _record(db, agent, cfg, resp.model or model, "ok", company_id, job_id, phash, attempts=attempts,
                      tin=tin, tout=tout, tcached=tcached, latency=start, output=out.model_dump(mode="json"))
        return AgentResult(out, run.id, model=resp.model or model)
    _record(db, agent, cfg, model, "invalid_output", company_id, job_id, phash, error=last_err, attempts=attempts,
            tin=tin, tout=tout, tcached=tcached, latency=start)
    raise AgentFailed(last_err or "Agent failed", retryable=False)


def _record(db, agent, cfg, model, status, company_id, job_id, phash, *, error=None, attempts=1, tin=0, tout=0,
            tcached=0, latency: float | None = None, output=None) -> AIRun:
    run = AIRun(
        agent=agent, provider=cfg.get("provider", "none"), model=model, status=status, input_tokens=tin,
        output_tokens=tout, cached_tokens=tcached, cost_usd=cost_usd(cfg, model, tin, tout, tcached),
        latency_ms=int((time.perf_counter() - latency) * 1000) if latency else 0, attempts=attempts,
        company_id=company_id, job_id=job_id, prompt_hash=phash, output=output or {}, error=error,
    )
    db.add(run)
    db.flush()
    return run
