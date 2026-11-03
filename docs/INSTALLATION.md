# Installation

## Requirements

* Docker 24+ with Compose v2 (for the containerised stack), **or**
* Python 3.12+ (3.13 tested), Node.js 20+ (22/24 tested), PostgreSQL 16, Redis 7 for local development.

## 1. Configure

```bash
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Put both values in `.env` and set `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`
(≥10 chars, three of: lower, upper, digit, symbol). **Back up `ENCRYPTION_KEY`** — without it stored
API keys and OAuth tokens cannot be decrypted.

Set `CRAWLER_CONTACT` to a URL or email that website owners can use to reach you. It is added to
the crawler's User-Agent and is required by Wikimedia's policy for the Wikidata source.

## 2a. Run everything in Docker

```bash
docker compose up -d --build
docker compose ps                 # api, worker, beat, frontend, postgres, redis should be healthy
```

* Dashboard: http://localhost:3000 (`FRONTEND_HOST_PORT`)
* API + OpenAPI docs: http://localhost:8000/api/docs (`API_HOST_PORT`)

The `api` container runs `alembic upgrade head` and `python -m app.cli bootstrap` on start
(creates the first admin and default workflow schedules).

## 2b. Local development

```bash
make dev-infra                                   # postgres (5434) + redis (6380) in Docker
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli bootstrap
cd .. && make api        # FastAPI on :8100 — the Next.js dev server proxies /api there (API_INTERNAL_URL)
make worker              # Celery worker (threads pool — macOS-safe)
make beat                # scheduler
cd frontend && npm install && npm run dev        # Next.js on :3000 (use `-- -p 3100` if 3000 is taken)
```

Create the test database once: `docker compose exec postgres psql -U agency -c "create database agency_test"`,
then `make test`.

## 3. First login

1. Sign in with the bootstrap admin.
2. Complete the onboarding wizard (agency profile, services, ICP, tone, case studies, sender details).
3. Settings → AI configuration: choose a provider and models, set a daily budget, press **Test**.
4. Settings → Integrations: optionally add a web-search API key and connect Gmail/Outlook.
5. Create a campaign and press **Run now**, or wait for the daily schedule.

## Optional: JavaScript rendering

Build the backend image with `--build-arg INSTALL_PLAYWRIGHT=true` and set `PLAYWRIGHT_ENABLED=true`.
Pages whose static HTML contains almost no text are then rendered in headless Chromium.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Docker build fails with `CERTIFICATE_VERIFY_FAILED … self-signed certificate in certificate chain` | Your network inspects TLS. Put your organisation's root CA (PEM, `.crt`) in `certs/` — see `certs/README.md`. On macOS: `security find-certificate -a -p /Library/Keychains/System.keychain > certs/local-system-keychain.crt`. |
| Celery jobs stay `queued` on macOS with `ValueError: not enough values to unpack` in the worker log | Use the threads pool locally (`make worker` already does). Docker/Linux uses the default prefork pool. |
| Wikidata source shows “Not configured” | Set `CRAWLER_CONTACT` (Wikimedia requires contact details in the User-Agent). |
| Port already in use | Change `API_HOST_PORT`, `FRONTEND_HOST_PORT`, `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT` in `.env`. |
| Jobs stuck after a crash | They are re-queued automatically within ~10 minutes; or Automation → Retry. |
