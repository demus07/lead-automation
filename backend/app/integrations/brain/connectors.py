"""Company Brain connectors — provider-independent access to authorised agency knowledge.

Each connector declares the credentials/config it needs, can test the connection, and returns
knowledge items (and optionally target-account company records). Imported items are stored with
``approved_for_outreach = False``; a human must approve each item before agents may reference it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.discovery.normalize import normalize_domain


class ConnectorError(Exception):
    pass


@dataclass
class BrainItem:
    title: str
    content: str
    source_ref: str
    url: str | None = None
    kind: str = "other"
    service: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class BrainCompany:
    name: str
    domain: str | None
    source_ref: str
    data: dict[str, Any] = field(default_factory=dict)


class BrainConnector(ABC):
    key = ""
    label = ""
    description = ""
    credential_fields: list[dict[str, str]] = []
    config_fields: list[dict[str, str]] = []
    supports_companies = False

    def describe(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "description": self.description,
                "credential_fields": self.credential_fields, "config_fields": self.config_fields,
                "requires_auth": bool(self.credential_fields), "supports_companies": self.supports_companies}

    @abstractmethod
    def test(self, creds: dict, config: dict) -> str: ...

    @abstractmethod
    def fetch_items(self, creds: dict, config: dict) -> list[BrainItem]: ...

    def fetch_companies(self, creds: dict, config: dict) -> list[BrainCompany]:
        return []


def _get(url: str, headers: dict, params: dict | None = None) -> dict:
    r = httpx.get(url, headers=headers, params=params, timeout=30)
    if r.status_code in (401, 403):
        raise ConnectorError(f"Authentication failed (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise ConnectorError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


# ------------------------------------------------------------------------------------- Notion
class NotionConnector(BrainConnector):
    key = "notion"
    label = "Notion"
    description = "Pages and databases shared with a Notion internal integration."
    credential_fields = [{"name": "token", "label": "Internal integration secret", "secret": "true"}]
    config_fields = [
        {"name": "page_ids", "label": "Knowledge page IDs (comma-separated)"},
        {"name": "database_ids", "label": "Knowledge database IDs (comma-separated)"},
        {"name": "accounts_database_id", "label": "Target-accounts database ID (optional, for discovery)"},
    ]
    supports_companies = True
    API = "https://api.notion.com/v1"

    def _h(self, creds):
        return {"Authorization": f"Bearer {creds.get('token', '')}", "Notion-Version": "2022-06-28"}

    def test(self, creds, config):
        me = _get(f"{self.API}/users/me", self._h(creds))
        return f"Connected as {me.get('name') or me.get('bot', {}).get('owner', {}).get('type', 'integration')}"

    def _page_text(self, creds, page_id: str, limit: int = 200) -> str:
        data = _get(f"{self.API}/blocks/{page_id}/children", self._h(creds), {"page_size": limit})
        out = []
        for b in data.get("results", []):
            rich = (b.get(b.get("type"), {}) or {}).get("rich_text", [])
            txt = "".join(t.get("plain_text", "") for t in rich)
            if txt:
                out.append(txt)
        return "\n".join(out)

    def _title(self, page: dict) -> str:
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "Untitled"
        return "Untitled"

    def fetch_items(self, creds, config):
        items: list[BrainItem] = []
        for pid in [p.strip() for p in (config.get("page_ids") or "").split(",") if p.strip()]:
            page = _get(f"{self.API}/pages/{pid}", self._h(creds))
            items.append(BrainItem(self._title(page), self._page_text(creds, pid)[:20000], f"notion:page:{pid}",
                                   page.get("url")))
        for dbid in [p.strip() for p in (config.get("database_ids") or "").split(",") if p.strip()]:
            r = httpx.post(f"{self.API}/databases/{dbid}/query", headers=self._h(creds), json={"page_size": 50},
                           timeout=30)
            if r.status_code >= 400:
                raise ConnectorError(f"Notion database {dbid}: HTTP {r.status_code}")
            for page in r.json().get("results", []):
                props = page.get("properties", {})
                kind = _select(props, ("Type", "Kind", "Category")) or "other"
                service = _select(props, ("Service",))
                items.append(BrainItem(self._title(page), self._page_text(creds, page["id"])[:20000],
                                       f"notion:page:{page['id']}", page.get("url"), _kind(kind), _service(service)))
        return items

    def fetch_companies(self, creds, config):
        dbid = (config.get("accounts_database_id") or "").strip()
        if not dbid:
            return []
        r = httpx.post(f"{self.API}/databases/{dbid}/query", headers=self._h(creds), json={"page_size": 100}, timeout=30)
        if r.status_code >= 400:
            raise ConnectorError(f"Notion accounts database: HTTP {r.status_code}")
        out = []
        for page in r.json().get("results", []):
            props = page.get("properties", {})
            website = None
            for name in ("Website", "Domain", "URL"):
                p = props.get(name)
                if p and p.get("type") == "url":
                    website = p.get("url")
                elif p and p.get("type") == "rich_text":
                    website = "".join(t.get("plain_text", "") for t in p.get("rich_text", [])) or None
                if website:
                    break
            out.append(BrainCompany(self._title(page), normalize_domain(website), f"notion:page:{page['id']}",
                                    {"notion_url": page.get("url")}))
        return out


def _select(props: dict, names: tuple[str, ...]) -> str | None:
    for n in names:
        p = props.get(n)
        if p and p.get("type") == "select" and p.get("select"):
            return p["select"].get("name")
    return None


KINDS = {"service", "pricing", "portfolio", "case_study", "testimonial", "positioning", "proposal", "messaging"}


def _kind(v: str | None) -> str:
    k = (v or "").lower().replace(" ", "_")
    return k if k in KINDS else "other"


def _service(v: str | None) -> str | None:
    s = (v or "").lower()
    if "brain" in s:
        return "company_brain"
    if "web" in s:
        return "website"
    return None


# ------------------------------------------------------------------------------------- Slack
class SlackConnector(BrainConnector):
    key = "slack"
    label = "Slack"
    description = "Pinned and recent messages from specific channels (bot token with channels:history, pins:read)."
    credential_fields = [{"name": "bot_token", "label": "Bot token (xoxb-…)", "secret": "true"}]
    config_fields = [{"name": "channel_ids", "label": "Channel IDs (comma-separated)"},
                     {"name": "pinned_only", "label": "Pinned messages only (true/false)"}]
    API = "https://slack.com/api"

    def _call(self, creds, method, params):
        j = _get(f"{self.API}/{method}", {"Authorization": f"Bearer {creds.get('bot_token', '')}"}, params)
        if not j.get("ok"):
            raise ConnectorError(f"Slack {method}: {j.get('error')}")
        return j

    def test(self, creds, config):
        j = self._call(creds, "auth.test", {})
        return f"Connected to workspace {j.get('team')}"

    def fetch_items(self, creds, config):
        items = []
        pinned_only = str(config.get("pinned_only", "true")).lower() != "false"
        for ch in [c.strip() for c in (config.get("channel_ids") or "").split(",") if c.strip()]:
            if pinned_only:
                msgs = [p.get("message", {}) for p in self._call(creds, "pins.list", {"channel": ch}).get("items", [])]
            else:
                msgs = self._call(creds, "conversations.history", {"channel": ch, "limit": 100}).get("messages", [])
            for m in msgs:
                text = m.get("text") or ""
                if len(text) < 40:
                    continue
                items.append(BrainItem(text.split("\n")[0][:120], text[:20000], f"slack:{ch}:{m.get('ts')}",
                                       m.get("permalink")))
        return items


# ------------------------------------------------------------------------------------- Microsoft Teams
class TeamsConnector(BrainConnector):
    key = "teams"
    label = "Microsoft Teams"
    description = ("Channel messages via Microsoft Graph (app registration with ChannelMessage.Read.All, admin "
                   "consent required).")
    credential_fields = [{"name": "tenant_id", "label": "Tenant ID", "secret": "false"},
                         {"name": "client_id", "label": "Client ID", "secret": "false"},
                         {"name": "client_secret", "label": "Client secret", "secret": "true"}]
    config_fields = [{"name": "team_id", "label": "Team ID"}, {"name": "channel_ids", "label": "Channel IDs"}]

    def _token(self, creds) -> str:
        r = httpx.post(f"https://login.microsoftonline.com/{creds.get('tenant_id')}/oauth2/v2.0/token", data={
            "client_id": creds.get("client_id"), "client_secret": creds.get("client_secret"),
            "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"}, timeout=20)
        if r.status_code != 200:
            raise ConnectorError(f"Microsoft token request failed: HTTP {r.status_code}")
        return r.json()["access_token"]

    def test(self, creds, config):
        self._token(creds)
        return "Token acquired"

    def fetch_items(self, creds, config):
        h = {"Authorization": f"Bearer {self._token(creds)}"}
        team = config.get("team_id")
        items = []
        for ch in [c.strip() for c in (config.get("channel_ids") or "").split(",") if c.strip()]:
            data = _get(f"https://graph.microsoft.com/v1.0/teams/{team}/channels/{ch}/messages", h, {"$top": 50})
            for m in data.get("value", []):
                import re as _re

                text = _re.sub(r"<[^>]+>", " ", (m.get("body") or {}).get("content", ""))
                if len(text.strip()) < 40:
                    continue
                items.append(BrainItem((m.get("subject") or text.strip()[:100]), text[:20000], f"teams:{ch}:{m['id']}",
                                       m.get("webUrl")))
        return items


# ------------------------------------------------------------------------------------- Company Brain API
class CompanyBrainAPIConnector(BrainConnector):
    key = "company_brain_api"
    label = "Company Brain (HTTP API)"
    description = ("Your own Company Brain deployment. GET {base_url}/knowledge returns items "
                   "[{id,title,content,url,kind,service}]; optional GET {base_url}/companies returns target accounts.")
    credential_fields = [{"name": "api_token", "label": "API token", "secret": "true"}]
    config_fields = [{"name": "base_url", "label": "Base URL"}]
    supports_companies = True

    def _h(self, creds):
        return {"Authorization": f"Bearer {creds.get('api_token', '')}"}

    def test(self, creds, config):
        _get(f"{config.get('base_url', '').rstrip('/')}/knowledge", self._h(creds), {"limit": 1})
        return "Connected"

    def fetch_items(self, creds, config):
        data = _get(f"{config.get('base_url', '').rstrip('/')}/knowledge", self._h(creds), {"limit": 500})
        rows = data if isinstance(data, list) else data.get("items", [])
        return [BrainItem(str(r.get("title", "Untitled"))[:300], str(r.get("content", ""))[:20000],
                          f"cb:{r.get('id')}", r.get("url"), _kind(r.get("kind")), _service(r.get("service")))
                for r in rows if r.get("id")]

    def fetch_companies(self, creds, config):
        data = _get(f"{config.get('base_url', '').rstrip('/')}/companies", self._h(creds), {"limit": 500})
        rows = data if isinstance(data, list) else data.get("items", [])
        return [BrainCompany(str(r.get("name")), normalize_domain(r.get("website") or r.get("domain")),
                             f"cb:{r.get('id')}", {k: r.get(k) for k in ("industry", "notes") if r.get(k)})
                for r in rows if r.get("name")]


CONNECTORS: dict[str, BrainConnector] = {c.key: c for c in [
    NotionConnector(), SlackConnector(), TeamsConnector(), CompanyBrainAPIConnector()]}
