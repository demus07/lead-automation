"""Discovery from authorised Company Brain connections (e.g. a Notion target-accounts database or the
Company Brain API's /companies endpoint)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.discovery.providers.base import DiscoveredCompany, DiscoveryProvider, DiscoveryQuery, ProviderError


class CompanyBrainProvider(DiscoveryProvider):
    key = "company_brain"
    label = "Company Brain (connected sources)"
    kind = "crm"
    requires_auth = True
    description = "Target accounts from authorised Company Brain connectors (Notion accounts DB, Company Brain API)."

    def _connections(self):
        from app.core.db import SessionLocal
        from app.integrations.brain.connectors import CONNECTORS
        from app.models import IntegrationConnection

        with SessionLocal() as db:
            rows = db.scalars(select(IntegrationConnection).where(
                IntegrationConnection.deleted_at.is_(None), IntegrationConnection.status == "connected")).all()
            return [(r, CONNECTORS[r.provider]) for r in rows
                    if r.provider in CONNECTORS and CONNECTORS[r.provider].supports_companies]

    def is_configured(self, cfg: dict[str, Any]) -> bool:
        try:
            return bool(self._connections())
        except Exception:  # noqa: BLE001
            return False

    def search(self, q: DiscoveryQuery, cfg: dict[str, Any]) -> list[DiscoveredCompany]:
        from app.core.crypto import decrypt

        out: list[DiscoveredCompany] = []
        conns = self._connections()
        if not conns:
            raise ProviderError("No connected Company Brain source provides target accounts")
        for row, connector in conns:
            creds = json.loads(decrypt(row.credentials_enc)) if row.credentials_enc else {}
            for c in connector.fetch_companies(creds, row.config):
                out.append(DiscoveredCompany(name=c.name, domain=c.domain, website=f"https://{c.domain}" if c.domain else None,
                                             source_url=None, source_title=f"{row.name} ({row.provider})",
                                             raw={"source_ref": c.source_ref, **c.data}))
        return out[q.offset: q.offset + q.limit]
