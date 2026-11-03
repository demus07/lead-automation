# Agency Growth Engine — Architecture

## 1. Goals and hard rules

* Discover → research → qualify → draft → **human approval** → unsent email draft → reply tracking.
* **No email is ever sent by the application.** There is no code path that calls Gmail `messages.send`,
  `drafts.send`, or Microsoft Graph `sendMail` / `/send`. A test (`test_no_send_code_paths`) greps the
  codebase to enforce this.
* The two services (Bespoke Websites, Company Brain) are scored **independently**; deterministic code
  picks at most one recommended service, or none.
* AI output is untrusted until validated. Agents have no tools and no database access: they receive
  sanitised, delimited data and return JSON that is validated by Pydantic and then cross-checked by
  deterministic code (evidence IDs must exist, quotes must appear in source text, numbers must be
  supported).
* External providers are optional. Everything degrades to a clearly reported "limited mode".

## 2. System diagram

```
                ┌──────────────────────────── Next.js dashboard (frontend/) ───────────────────────────┐
                │ Overview · Discovery · Companies · Contacts · Research · Pipeline · Approvals · ...   │
                └───────────────▲──────────────────────────────────────────────────────────────────────┘
                                │ HTTPS, httpOnly session cookie + CSRF header
┌───────────────────────────────┴───────────────────────────────────────────────────────────────────────┐
│ FastAPI (backend/app)                                                                                  │
│  api/  ── auth, RBAC, rate limiting, validation, audit logging                                         │
│  services/ ── CRM, state machine, dedupe, suppression, approvals, analytics, CSV, settings             │
│  workflows/ ── internal workflow engine (runs, steps, idempotency keys, pause/resume, retries)         │
│  discovery/ ── provider abstraction: Wikidata, YC directory, HN hiring, RSS, SEC Form D, Brave,        │
│                Tavily, SearXNG, SerpAPI, CSV                                                           │
│  research/ ── robots-aware fetcher, crawler, extractor, measurable site audit, signals, contacts,      │
│               email verification (syntax + MX; never "verified" without a verifier)                   │
│  ai/ ── LLM provider abstraction (OpenAI-compatible, Anthropic, fake), agents, prompts, sanitiser,     │
│         usage + cost tracking, budgets                                                                │
│  integrations/ ── Gmail + Outlook OAuth2 (drafts + metadata only), Company Brain connectors            │
└───────┬─────────────────────────────────────┬───────────────────────────────────────────────────────────┘
        │ SQLAlchemy                          │ Celery tasks
┌───────▼────────┐                   ┌────────▼─────────┐     ┌──────────────────┐
│ PostgreSQL 16  │                   │ Redis (broker,   │◀────│ Celery beat      │
│ JSONB, UUIDs   │◀──────────────────│ rate limits)     │     │ (scheduler tick) │
└────────────────┘   Celery worker   └──────────────────┘     └──────────────────┘
```

## 3. Directory structure

```
backend/
  app/
    main.py                 FastAPI app factory, middleware, routers
    worker.py               Celery app + beat schedule
    core/                   config, db, security (passwords, JWT, CSRF), crypto (Fernet),
                            rate limiting, logging, errors, deps (auth/RBAC)
    models/                 SQLAlchemy models (one module per domain)
    schemas/                Pydantic request/response models
    api/                    Routers (auth, users, settings, campaigns, discovery, companies, contacts,
                            research, opportunities, drafts, approvals, email, conversations, tasks,
                            suppression, workflows, ai_usage, analytics, integrations, knowledge, audit)
    services/               Deterministic business logic
    discovery/              Discovery providers + engine
    research/               Crawler, extraction, audit, signals, contacts
    ai/                     LLM providers, agents, prompts/, sanitiser, usage tracking
    integrations/           email/ (gmail, outlook, oauth), brain/ (notion, slack, msgraph, manual)
    workflows/              Engine + the seven workflows + scheduler
  alembic/                  Migrations
  tests/                    pytest suite (unit + integration + acceptance)
frontend/                   Next.js 15, TypeScript, Tailwind, shadcn/ui
docs/                       Architecture, install, deployment, backup, integrations, user manual, API
docker-compose.yml          postgres, redis, api, worker, beat, frontend, backup
.env.example
```

## 4. Database design

All tables: `id UUID PK`, `created_at`, `updated_at`; domain tables also have `deleted_at` (soft delete).

| Table | Purpose | Key constraints |
|---|---|---|
| users | Accounts, roles (`admin`, `operator`, `viewer`) | unique lower(email) |
| settings | Key/value JSONB settings (agency profile, LLM, discovery, quality thresholds, retention, budgets). Secret values are Fernet-encrypted | unique key |
| campaigns | Discovery campaign configuration (industries, geos, sizes, roles, query templates, sources, daily limits, schedule) | |
| search_queries | Every query executed: provider, text, params, status, result count, error | idx campaign_id, created_at |
| companies | Company records, `domain_normalized`, status, scores snapshot, research timestamps | **unique domain_normalized where deleted_at is null** |
| lead_sources | Provenance: which provider/query/URL found a company or contact, raw evidence | idx company_id |
| contacts | Decision-makers: name, title, email, `email_normalized`, `email_status`, profile URL, source URL/type, confidence | **unique email_normalized where not null and not deleted** |
| research_reports | Website crawl + analysis: pages, measurable audit, categorised observations (fact/observation/hypothesis/unknown), evidence | idx company_id, version |
| buying_signals | Typed signals with source URL, published/discovered dates, evidence, confidence, freshness | unique (company_id, source_url, signal_type) |
| opportunities | Current opportunity per company: both scores, recommended service, angle | unique company_id |
| lead_scores | Score history: service, score, factors, evidence, confidence, method (llm/heuristic) | idx company_id, created_at |
| outreach_drafts | Generated messages, evidence used, quality score + report, status, version | idx status |
| approvals | Every approval-queue action (approve/edit/reject/later/regenerate/DNC) with actor + diff | idx draft_id |
| email_accounts | Connected Gmail/Outlook accounts, encrypted tokens, scopes, status | unique (provider, email) |
| email_drafts | Unsent drafts created in mailbox: external draft/message/thread IDs | **unique idempotency_key**, unique (outreach_draft_id, email_account_id) |
| interactions | Inbound/outbound messages, classification, suggested reply | unique (email_account_id, external_message_id) |
| tasks | Follow-ups/reminders | idx due_at |
| suppression_list | Do-not-contact by email or domain, never hard-deleted | unique (kind, value) |
| automation_jobs | Workflow runs: workflow, trigger, status, idempotency key, attempts, stats, errors | unique idempotency_key |
| ai_runs | Each LLM call: agent, provider, model, tokens, cost, latency, status, company | idx agent, created_at |
| audit_logs | Append-only actions by users and system | idx entity, created_at |
| notes | Free-form CRM notes | |
| knowledge_items | Agency knowledge (services, case studies, testimonials…) with `approved_for_outreach` / `confidential` flags, from manual entry or Company Brain connectors | |
| integration_connections | Company Brain connector configs (encrypted credentials) | |
| workflow_schedules | Per-workflow cron, enabled/paused, limits, last/next run | unique workflow |
| page_cache | Fetched pages (URL hash, status, content hash, text) to avoid re-crawling | unique url_hash |

### Lead status state machine

```
NEW → RESEARCHING → RESEARCHED → QUALIFIED → DRAFT_GENERATED → PENDING_APPROVAL → APPROVED
    → EMAIL_DRAFT_CREATED → CONTACTED → REPLIED → {INTERESTED, MEETING_REQUESTED, NOT_INTERESTED}
Any non-terminal → DISQUALIFIED;  Any → DO_NOT_CONTACT (terminal, sticky)
```
Transitions are defined in `services/state_machine.py`; illegal transitions raise and are rejected
by the API. Every transition is audit-logged.

## 5. Scoring design (deterministic aggregation of evidence-backed ratings)

The Opportunity Scoring Agent rates each factor 0–5 and must cite evidence IDs drawn from the research
report/signals. Deterministic code:
1. Drops any factor rating whose evidence IDs don't exist (or rates it as "unknown" = neutral-low).
2. Computes `score = Σ weight_i × rating_i / 5 × 100`.
3. Computes confidence from evidence coverage and freshness.
4. Picks the recommended service: highest score ≥ `qualification_threshold` (default 60) and ≥ the
   other by `service_margin` (default 10) **or** if both qualify, the higher; otherwise `none`.

When no LLM is configured, a transparent heuristic scorer (marked `method=heuristic`) uses measurable
audit results and signals so qualification still works in limited mode.

## 6. Prompt-injection defences

1. Web content is sanitised (scripts/styles/comments/hidden elements/zero-width chars removed).
2. Injection heuristics flag pages ("ignore previous instructions", role markers, etc.); flagged text
   is still treated purely as data and the flag is stored with the report.
3. Untrusted content is wrapped in `<untrusted_content id=...>` blocks; the system prompt states that
   nothing inside them is an instruction.
4. Agents have no tools. Outputs are JSON validated against Pydantic schemas.
5. All writes, state transitions and permission checks are done by deterministic code.
6. Quotes/evidence returned by agents are verified against stored source text.

## 7. Development plan

| Phase | Scope | Verification |
|---|---|---|
| 1 Foundation | structure, config, DB models, Alembic, auth/RBAC/CSRF, audit, Docker, dashboard shell | pytest auth/RBAC, migrations up/down, compose health |
| 2 Discovery | provider abstraction, public sources, CSV import, dedupe, campaigns, CRM basics | TEST 1–3 |
| 3 Intelligence | fetcher/robots/crawler, extraction, site audit, research agent, signals, contacts | TEST 4, 5, 8, 9 |
| 4 Qualification | scoring agent + deterministic aggregation, heuristic fallback | TEST 6, 7 |
| 5 Outreach | onboarding, writer + quality agents, draft management, suppression | TEST 10–12, 18 |
| 6 Approval | approval queue, Gmail/Outlook OAuth + drafts, idempotency | TEST 13–16 |
| 7 CRM/Analytics | replies, classification, opt-outs, analytics, AI usage | TEST 17, 19 |
| 8 Hardening | rate limiting, retention, backups, monitoring, docs, recovery | TEST 20 |
