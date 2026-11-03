"""Agency knowledge base + Company Brain connectors."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api._common import PageParams, get_or_404, like, paginate
from app.core.crypto import decrypt, encrypt
from app.core.db import get_db
from app.core.deps import require_admin, require_operator, require_viewer
from app.integrations.brain.connectors import CONNECTORS, ConnectorError
from app.models import IntegrationConnection, KnowledgeItem, User
from app.models.base import utcnow
from app.schemas.common import ORM, Msg
from app.services.audit import audit

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
KINDS = "^(service|pricing|portfolio|case_study|testimonial|positioning|proposal|messaging|other)$"


class KnowledgeOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    content: str
    url: str | None
    service: str | None
    tags: list[str]
    source: str
    source_ref: str | None
    connection_id: uuid.UUID | None
    approved_for_outreach: bool
    confidential: bool
    updated_at: datetime


class KnowledgeIn(BaseModel):
    kind: str = Field(pattern=KINDS)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field("", max_length=50_000)
    url: str | None = Field(None, max_length=1000)
    service: str | None = Field(None, pattern="^(website|company_brain|both)$")
    tags: list[str] = Field(default_factory=list)
    approved_for_outreach: bool = False
    confidential: bool = False


class KnowledgePatch(BaseModel):
    kind: str | None = Field(None, pattern=KINDS)
    title: str | None = Field(None, min_length=1, max_length=300)
    content: str | None = Field(None, max_length=50_000)
    url: str | None = None
    service: str | None = Field(None, pattern="^(website|company_brain|both)$")
    tags: list[str] | None = None
    approved_for_outreach: bool | None = None
    confidential: bool | None = None


@router.get("")
def list_items(q: str | None = Query(None, max_length=200), kind: str | None = None, approved: bool | None = None,
               pp: PageParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    stmt = select(KnowledgeItem).where(KnowledgeItem.deleted_at.is_(None))
    if q:
        stmt = stmt.where(KnowledgeItem.title.ilike(like(q)) | KnowledgeItem.content.ilike(like(q)))
    if kind:
        stmt = stmt.where(KnowledgeItem.kind == kind)
    if approved is not None:
        stmt = stmt.where(KnowledgeItem.approved_for_outreach.is_(approved))
    return paginate(db, stmt.order_by(KnowledgeItem.updated_at.desc()), pp,
                    lambda k: KnowledgeOut.model_validate(k).model_dump())


@router.post("", status_code=201)
def create_item(body: KnowledgeIn, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    if body.approved_for_outreach and body.confidential:
        raise HTTPException(422, "Confidential items cannot be approved for outreach")
    k = KnowledgeItem(**body.model_dump(), source="manual")
    db.add(k)
    db.flush()
    audit(db, "knowledge.created", actor=user, entity_type="knowledge_item", entity_id=k.id)
    db.commit()
    return KnowledgeOut.model_validate(k)


@router.patch("/{item_id}")
def update_item(item_id: uuid.UUID, body: KnowledgePatch, db: Session = Depends(get_db),
                user: User = Depends(require_operator)):
    k = get_or_404(db, KnowledgeItem, item_id)
    ch = body.model_dump(exclude_unset=True)
    for f, v in ch.items():
        setattr(k, f, v)
    if k.approved_for_outreach and k.confidential:
        raise HTTPException(422, "Confidential items cannot be approved for outreach")
    audit(db, "knowledge.updated", actor=user, entity_type="knowledge_item", entity_id=k.id, detail={"fields": list(ch)})
    db.commit()
    return KnowledgeOut.model_validate(k)


@router.delete("/{item_id}", response_model=Msg)
def delete_item(item_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_operator)):
    k = get_or_404(db, KnowledgeItem, item_id)
    k.deleted_at = utcnow()
    db.commit()
    return Msg(message="Deleted")


# ------------------------------------------------------------------------------ connectors
class ConnectionIn(BaseModel):
    provider: str
    name: str = Field(min_length=1, max_length=200)
    credentials: dict[str, str] = Field(default_factory=dict)
    config: dict[str, str] = Field(default_factory=dict)


def conn_out(c: IntegrationConnection) -> dict:
    connector = CONNECTORS.get(c.provider)
    return {"id": c.id, "provider": c.provider, "name": c.name, "status": c.status, "config": c.config,
            "credentials_set": bool(c.credentials_enc), "last_synced_at": c.last_synced_at, "last_error": c.last_error,
            "connector": connector.describe() if connector else None, "created_at": c.created_at}


@router.get("/connectors")
def connectors(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    rows = db.scalars(select(IntegrationConnection).where(IntegrationConnection.deleted_at.is_(None))).all()
    return {"available": [c.describe() for c in CONNECTORS.values()], "connections": [conn_out(c) for c in rows],
            "note": "Gmail and Outlook mailboxes are connected under Email accounts and are used only for drafts "
                    "and reply tracking, not as knowledge sources."}


@router.post("/connectors", status_code=201)
def create_connection(body: ConnectionIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    connector = CONNECTORS.get(body.provider)
    if not connector:
        raise HTTPException(404, "Unknown connector")
    allowed_cfg = {f["name"] for f in connector.config_fields}
    allowed_creds = {f["name"] for f in connector.credential_fields}
    c = IntegrationConnection(provider=body.provider, name=body.name,
                              config={k: v for k, v in body.config.items() if k in allowed_cfg},
                              credentials_enc=encrypt(json.dumps({k: v for k, v in body.credentials.items()
                                                                  if k in allowed_creds})) if body.credentials else None,
                              status="not_configured" if not body.credentials and connector.credential_fields else "configured")
    db.add(c)
    db.flush()
    audit(db, "connector.created", actor=user, entity_type="integration_connection", entity_id=c.id,
          detail={"provider": c.provider})
    db.commit()
    return conn_out(c)


def _creds(c: IntegrationConnection) -> dict:
    return json.loads(decrypt(c.credentials_enc)) if c.credentials_enc else {}


@router.post("/connectors/{cid}/test")
def test_connection(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = get_or_404(db, IntegrationConnection, cid)
    try:
        msg = CONNECTORS[c.provider].test(_creds(c), c.config)
        c.status, c.last_error = "connected", None
    except (ConnectorError, Exception) as e:  # noqa: BLE001
        c.status, c.last_error, msg = "error", str(e)[:500], str(e)
    db.commit()
    return {"status": c.status, "message": msg}


@router.post("/connectors/{cid}/sync")
def sync_connection(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = get_or_404(db, IntegrationConnection, cid)
    try:
        items = CONNECTORS[c.provider].fetch_items(_creds(c), c.config)
    except (ConnectorError, Exception) as e:  # noqa: BLE001
        c.status, c.last_error = "error", str(e)[:500]
        db.commit()
        raise HTTPException(502, f"Sync failed: {e}") from None
    created = updated = 0
    for it in items:
        k = db.scalar(select(KnowledgeItem).where(KnowledgeItem.source_ref == it.source_ref))
        if k is None:
            k = KnowledgeItem(source=c.provider, source_ref=it.source_ref, connection_id=c.id, kind=it.kind,
                              title=it.title, content=it.content, url=it.url, service=it.service, tags=it.tags,
                              approved_for_outreach=False, confidential=False)
            db.add(k)
            created += 1
        else:
            k.title, k.content, k.url = it.title, it.content, it.url  # keep human approval flags
            updated += 1
    c.status, c.last_error, c.last_synced_at = "connected", None, utcnow()
    audit(db, "connector.synced", actor=user, entity_type="integration_connection", entity_id=c.id,
          detail={"created": created, "updated": updated})
    db.commit()
    return {"created": created, "updated": updated,
            "note": "Imported items are not approved for outreach until you approve them."}


@router.delete("/connectors/{cid}", response_model=Msg)
def delete_connection(cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = get_or_404(db, IntegrationConnection, cid)
    c.deleted_at, c.credentials_enc, c.status = utcnow(), None, "not_configured"
    db.commit()
    return Msg(message="Connector removed and credentials deleted")
