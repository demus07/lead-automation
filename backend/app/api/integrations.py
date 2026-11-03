"""Single status view of every optional integration: Connected / Not configured / Authentication expired / Error."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.llm.providers import llm_available
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_viewer
from app.discovery.providers import all_providers
from app.integrations.brain.connectors import CONNECTORS
from app.integrations.email.service import get_mailbox_provider
from app.models import EmailAccount, IntegrationConnection, User
from app.services import settings_service

router = APIRouter(prefix="/api/integrations", tags=["integrations"])
STATUS_LABEL = {"connected": "Connected", "available": "Connected", "configured": "Connected",
                "not_configured": "Not configured", "expired": "Authentication expired", "revoked": "Authentication expired",
                "error": "Error"}


def _row(key, label, category, status, detail="", requires_auth=True, configure_at=""):
    return {"key": key, "label": label, "category": category, "status": status,
            "status_label": STATUS_LABEL.get(status, status), "detail": detail, "requires_auth": requires_auth,
            "configure_at": configure_at}


@router.get("")
def integration_status(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    s = get_settings()
    llm = settings_service.get_section(db, "llm")
    disc = settings_service.get_section(db, "discovery")
    enr = settings_service.get_section(db, "enrichment")
    rows = []
    rows.append(_row("llm", f"LLM ({llm['provider']})", "ai", "connected" if llm_available(llm) else "not_configured",
                     f"fast: {llm['model_fast']}, smart: {llm['model_smart']}", True, "/settings/ai"))
    for p in all_providers():
        st = p.status(disc)
        if p.kind == "web_search" and disc.get("web_search_provider") != p.key and st.status != "not_configured":
            detail = "Configured but not selected as the active web search provider"
        else:
            detail = st.detail or p.description
        rows.append(_row(f"discovery:{p.key}", p.label, "discovery", st.status, detail, p.requires_auth,
                         "/settings/integrations"))
    rows.append(_row("enrichment:hunter", "Hunter email verification", "enrichment",
                     "connected" if enr.get("verification_provider") == "hunter" and enr.get("hunter_api_key")
                     else "not_configured", "Optional mailbox verification. Without it emails are never marked verified.",
                     True, "/settings/integrations"))
    accts = db.scalars(select(EmailAccount).where(EmailAccount.deleted_at.is_(None))).all()
    for prov in ("gmail", "outlook"):
        mine = [a for a in accts if a.provider == prov]
        if not get_mailbox_provider(prov).configured():
            st, detail = "not_configured", "OAuth client credentials missing on the server (.env)"
        elif not mine:
            st, detail = "not_configured", "OAuth ready — no mailbox connected yet"
        else:
            worst = next((a for a in mine if a.status != "connected"), mine[0])
            st, detail = worst.status, ", ".join(f"{a.email} ({a.status})" for a in mine)
        rows.append(_row(f"email:{prov}", "Gmail" if prov == "gmail" else "Microsoft Outlook", "email", st, detail,
                         True, "/settings/integrations"))
    conns = db.scalars(select(IntegrationConnection).where(IntegrationConnection.deleted_at.is_(None))).all()
    for key, c in CONNECTORS.items():
        mine = [x for x in conns if x.provider == key]
        st = mine[0].status if mine else "not_configured"
        rows.append(_row(f"brain:{key}", c.label, "company_brain", st,
                         (mine[0].last_error or mine[0].name) if mine else c.description, bool(c.credential_fields),
                         "/settings/knowledge"))
    rows.append(_row("playwright", "Playwright JS rendering", "research",
                     "connected" if s.playwright_enabled else "not_configured",
                     "Renders JavaScript-heavy sites when enabled (PLAYWRIGHT_ENABLED=true + browsers installed).", False))
    return {"integrations": rows}
