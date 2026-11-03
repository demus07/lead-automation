"""Typed, DB-backed application settings with encrypted secret fields.

Each settings *section* has defaults and a list of secret field paths (dot notation). Secrets are
stored encrypted and never returned by the API — only masked values and an `is_set` flag.
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt, mask
from app.models import Setting, User

DEFAULTS: dict[str, dict[str, Any]] = {
    "agency_profile": {
        "onboarding_completed": False,
        "agency_name": "",
        "website": "",
        "description": "",
        "sender_name": "",
        "sender_title": "",
        "signature": "",
        "services": [
            {
                "key": "website",
                "name": "Bespoke websites & digital experiences",
                "description": "",
                "enabled": True,
            },
            {
                "key": "company_brain",
                "name": "Company Brain (AI company-intelligence layer)",
                "description": "",
                "enabled": True,
            },
        ],
        "target_industries": [],
        "target_geographies": [],
        "ideal_client_profile": "",
        "typical_budgets": "",
        "case_studies": [],  # [{title, summary, url, service}]
        "portfolio_links": [],
        "testimonials": [],  # [{quote, author, company, approved}]
        "tone": "Human, founder-led, specific, concise, conversational. Not salesy.",
        "call_to_action": "Open to a short call next week?",
        "postal_address": "",  # required for commercial email in some jurisdictions (e.g. CAN-SPAM)
        "include_opt_out_line": True,
        "opt_out_line": "If this isn't relevant, just reply 'no thanks' and I won't follow up.",
    },
    "llm": {
        "provider": "none",  # none | openai_compatible | anthropic
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model_fast": "gpt-4o-mini",  # extraction / classification
        "model_smart": "gpt-4o",  # research analysis / scoring / writing
        "temperature": 0.3,  # ignored for Anthropic models (current Claude models reject sampling params)
        "effort_fast": "low",  # Anthropic only: output_config.effort for the fast tier
        "effort_smart": "medium",
        "max_output_tokens": 1800,
        "daily_budget_usd": 5.0,
        "max_calls_per_company": 12,
        "max_retries": 2,
        "timeout_seconds": 90,
        "json_mode": True,
        # USD per 1M tokens; used for cost tracking. Override for your provider/model.
        "pricing": {
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
            "gpt-4.1": {"input": 2.00, "output": 8.00},
            "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01},
            "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20},
            "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20},
        },
    },
    "discovery": {
        "web_search_provider": "none",  # none | brave | tavily | serpapi | searxng
        "brave_api_key": "",
        "tavily_api_key": "",
        "serpapi_api_key": "",
        "searxng_url": "",
        "daily_search_quota": 100,
        "default_country": "",
        "results_per_query": 10,
        "excluded_domains": [
            "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
            "wikipedia.org", "crunchbase.com", "glassdoor.com", "indeed.com", "medium.com",
            "github.com", "google.com", "apple.com", "amazon.com", "reddit.com", "bloomberg.com",
            "techcrunch.com", "forbes.com", "reuters.com", "prnewswire.com", "businesswire.com",
            "globenewswire.com", "ycombinator.com", "news.ycombinator.com", "sec.gov", "wikidata.org",
        ],
        "sec_user_agent_contact": "",  # SEC requires a contact in the UA for EDGAR access
    },
    "enrichment": {
        "verification_provider": "none",  # none | hunter
        "hunter_api_key": "",
        "allow_mx_check": True,
    },
    "research": {
        "max_pages": 8,
        "request_delay_seconds": 1.5,
        "recrawl_after_days": 14,
        "signal_lookback_days": 365,
        "fresh_signal_days": 90,
        "recent_signal_days": 180,
        "use_news_rss": True,
    },
    "scoring": {
        "qualification_threshold": 60,
        "service_margin": 10,
        "min_confidence": 0.35,
    },
    "quality": {
        "threshold": 75,
        "max_regenerations": 2,
        "min_words": 60,
        "max_words": 140,
        "target_min_words": 70,
        "target_max_words": 120,
        "banned_phrases": [
            "I hope this email finds you well", "I came across your", "game-changer", "game changer",
            "revolutionize", "revolutionise", "synergy", "cutting-edge", "best-in-class", "world-class",
            "leverage", "unlock", "delve", "in today's fast-paced", "I was impressed", "I love what you",
            "touch base", "circle back", "quick question", "just checking in", "guarantee",
        ],
    },
    "retention": {
        "page_cache_days": 30,
        "ai_runs_days": 180,
        "audit_log_days": 730,
        "rejected_drafts_days": 180,
        "disqualified_companies_days": 365,
        "interactions_days": 730,
    },
}

SECRETS: dict[str, list[str]] = {
    "llm": ["api_key"],
    "discovery": ["brave_api_key", "tavily_api_key", "serpapi_api_key"],
    "enrichment": ["hunter_api_key"],
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "pricing":
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _row(db: Session, key: str) -> Setting | None:
    return db.scalar(select(Setting).where(Setting.key == key))


def get_section(db: Session, key: str) -> dict[str, Any]:
    """Merged settings with secrets decrypted (internal use only)."""
    if key not in DEFAULTS:
        raise KeyError(key)
    row = _row(db, key)
    value = _deep_merge(DEFAULTS[key], row.value if row else {})
    for f in SECRETS.get(key, []):
        enc = value.get(f)
        if enc and isinstance(enc, str) and enc.startswith("enc:"):
            try:
                value[f] = decrypt(enc[4:])
            except ValueError:
                value[f] = ""
    return value


def public_section(db: Session, key: str) -> dict[str, Any]:
    """Settings safe to return to the browser (secrets masked)."""
    value = get_section(db, key)
    for f in SECRETS.get(key, []):
        secret = value.get(f)
        value[f] = ""
        value[f"{f}_is_set"] = bool(secret)
        value[f"{f}_masked"] = mask(secret)
    return value


def update_section(db: Session, key: str, patch: dict[str, Any], user: User | None = None) -> dict[str, Any]:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = _row(db, key)
    stored = dict(row.value) if row else {}
    secret_fields = SECRETS.get(key, [])
    for k, v in patch.items():
        if k.endswith("_is_set") or k.endswith("_masked"):
            continue
        if k not in DEFAULTS[key]:
            continue  # ignore unknown keys
        if k in secret_fields:
            if v is None or v == "":
                continue  # blank → keep existing secret
            if v == "__clear__":
                stored[k] = ""
                continue
            stored[k] = "enc:" + encrypt(str(v))
        else:
            stored[k] = v
    if row is None:
        row = Setting(key=key, value=stored, secret_fields=secret_fields)
        db.add(row)
    else:
        row.value = stored
    row.updated_by_id = user.id if user else None
    db.flush()
    return public_section(db, key)
