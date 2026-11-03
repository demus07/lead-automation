# Agency Growth Engine

AI-assisted lead discovery, website & business research, opportunity qualification and outreach drafting
for a digital agency — with a **mandatory human approval step**. The application never sends email:
approval creates an *unsent* draft in your Gmail or Outlook mailbox, and you send it yourself.

```
discover → research → find contacts → score (Website / Company Brain, independently)
        → draft → quality gate → HUMAN APPROVAL → unsent mailbox draft → reply tracking → analytics
```

## What's inside

| Area | Implementation |
|---|---|
| Backend | FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, PostgreSQL 16 (JSONB, UUIDs) |
| Jobs | Celery + Redis, DB-driven scheduler (cron per workflow), retries, pause/resume, idempotency, recovery |
| Frontend | Next.js 15, TypeScript, Tailwind, shadcn/ui |
| Discovery | YC directory, Wikidata, HN “Who is hiring”, RSS, Brave / Tavily / SerpAPI / SearXNG (optional), CSV import, Company Brain connectors |
| Research | robots.txt-aware crawler (httpx + BeautifulSoup, optional Playwright), measurable site audit, careers/news signals, contact extraction |
| AI | Provider-independent: OpenAI-compatible APIs (OpenAI, Azure gateways, OpenRouter, Ollama, vLLM…) or Anthropic Claude. 9 agents with schema-validated JSON, evidence validation, token/cost tracking, budgets |
| Email | Gmail API & Microsoft Graph via OAuth2 — draft creation + reply metadata only (no send scope on Outlook; no send calls anywhere) |
| Compliance | Suppression list, opt-out detection, audit log, retention, data export & erasure, prompt-injection defences |

## Quick start (Docker)

```bash
cp .env.example .env            # set SECRET_KEY, ENCRYPTION_KEY, BOOTSTRAP_ADMIN_* at minimum
docker compose up -d --build
open http://localhost:3000       # sign in with BOOTSTRAP_ADMIN_EMAIL / PASSWORD
```

Then follow the onboarding wizard (agency profile → AI provider → search provider → email account).
Without an LLM or search API key the app runs in a clearly labelled **limited mode**.

## Documentation

* [Architecture](docs/ARCHITECTURE.md) — components, database design, state machine, scoring, security model
* [Installation](docs/INSTALLATION.md) — local development and Docker
* [Deployment](docs/DEPLOYMENT.md) — production checklist, reverse proxy, scaling, monitoring
* [Backup & recovery](docs/BACKUP_RECOVERY.md)
* [Integration configuration](docs/INTEGRATIONS.md) — LLMs, search providers, Gmail, Outlook, Company Brain connectors
* [User manual](docs/USER_MANUAL.md)
* [API](docs/API.md) — plus live OpenAPI at `/api/docs`
* [Security & compliance](docs/SECURITY.md)
* [Acceptance tests](docs/ACCEPTANCE_TESTS.md) — the 20 required tests and where each is verified

## Tests

```bash
make dev-infra && make test        # automated suite (mocked providers; CI-safe)
make test-live                     # tests against real public sources
```
