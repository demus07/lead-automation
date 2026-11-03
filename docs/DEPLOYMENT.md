# Deployment guide

## Topology

```
Internet ──TLS──▶ reverse proxy (Caddy / nginx / Traefik)
                    ├── /api/*  → api:8000      (FastAPI, 2+ uvicorn workers)
                    └── /*      → frontend:3000 (Next.js standalone)
api, worker, beat ─▶ postgres:5432 (persistent volume `pgdata`)
                  └▶ redis:6379    (broker + rate-limit counters, AOF persistence)
```

Serve the frontend and API from **one origin** (the frontend also proxies `/api` itself). The session
cookie is `SameSite=Lax` + httpOnly; CSRF uses a double-submit token bound to the session.

## Production checklist

| Item | Setting |
|---|---|
| Environment | `ENVIRONMENT=production` (the app refuses to start without real `SECRET_KEY` and `ENCRYPTION_KEY`) |
| HTTPS | `COOKIE_SECURE=true` (also enables HSTS) |
| Origins | `CORS_ORIGINS=https://growth.youragency.com`, `PUBLIC_APP_URL`, `PUBLIC_API_URL` |
| Database | strong `POSTGRES_PASSWORD`; do not publish port 5432 publicly (remove the `ports:` mapping) |
| Redis | do not publish 6379 publicly |
| OAuth | register redirect URIs exactly: `{PUBLIC_API_URL}/api/email/oauth/gmail/callback` and `/outlook/callback` |
| Crawler | `CRAWLER_CONTACT` set to a real contact |
| Bootstrap | remove `BOOTSTRAP_ADMIN_PASSWORD` from `.env` after the first start |
| Backups | schedule `docker compose --profile backup run --rm backup` (see Backup & recovery) |
| AI spend | set `daily_budget_usd` and `max_calls_per_company` in Settings → AI |

Example Caddyfile:

```
growth.youragency.com {
    encode gzip
    reverse_proxy /api/* api:8000
    reverse_proxy frontend:3000
}
```

## Scaling

* **API**: stateless; run several replicas or `uvicorn --workers N`.
* **Workers**: scale the `worker` service; queues are split (`default`, `research`, `ai`, `email`) so you
  can dedicate workers, e.g. `celery -A app.worker worker -Q research --concurrency 8`.
* **Beat**: run exactly **one** beat instance. Scheduled runs are also de-duplicated by idempotency key.
* Job safety: tasks are `acks_late` with `reject_on_worker_lost`; `recover_stale_jobs` (every 5 min)
  re-queues jobs orphaned by a crashed worker.

## Health & monitoring

* `GET /api/health` → `{"status","database","redis"}` (503 if the database is unreachable). Used by the
  compose health checks.
* Logs are JSON in production (`ENVIRONMENT=production`) with request IDs (`X-Request-ID`).
* Automation → job history shows every run, its log, errors and retries; failed jobs in the last 7 days
  appear on the dashboard.
* AI usage dashboard: spend per day/agent/model; budget blocks are recorded as `budget_blocked` runs.
* Suggested alerts: health endpoint non-200, `failed` jobs > 0 per day, email accounts in `expired`
  status (Integrations page), AI spend ≥ 80% of budget.

## Upgrades

```bash
git pull
docker compose build
docker compose up -d          # api runs `alembic upgrade head` on start
```

Take a backup before upgrading. Migrations are forward-only in production; `alembic downgrade` is
available for development.

## Performance notes

* Website research is I/O bound and rate-limited per host (robots `Crawl-delay` or `request_delay_seconds`,
  default 1.5 s). Pages are cached in `page_cache` and not refetched within `recrawl_after_days`.
* Identical AI prompts within 7 days reuse the stored result (duplicate-research prevention).
* Typical throughput with 4 workers: ~100–200 companies researched per hour (dominated by politeness delays).
