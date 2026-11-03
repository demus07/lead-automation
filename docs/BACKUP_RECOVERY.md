# Backup & recovery

## What to back up

| Asset | Where | How |
|---|---|---|
| Database (all CRM data, research, drafts, suppression list, audit log) | `pgdata` volume | `pg_dump` (below) |
| `ENCRYPTION_KEY` and `SECRET_KEY` | `.env` | store in your password manager / secret store — **without the encryption key, stored API keys and OAuth tokens are unrecoverable** (accounts would need reconnecting) |
| Redis | `redisdata` volume | not required — it only holds queued tasks and rate-limit counters; jobs are persisted in PostgreSQL and re-queued by recovery |

## Taking backups

```bash
make backup                      # = docker compose --profile backup run --rm backup
ls backups/                      # agency-20261103T060000Z.dump …
```

`scripts/backup.sh` writes a compressed custom-format dump, verifies it with `pg_restore -l`, and keeps
the newest `BACKUP_KEEP` (default 14) files.

Schedule it (host crontab example, daily 02:00):

```
0 2 * * * cd /opt/agency-growth-engine && docker compose --profile backup run --rm backup >> backups/backup.log 2>&1
```

Copy `backups/` off-host (S3/B2 with versioning, or another server). Encrypt at rest — the dump
contains business contact data.

## Restoring

```bash
./scripts/restore.sh backups/agency-20261103T060000Z.dump
```

The script asks for confirmation, stops `api/worker/beat`, restores with `--clean --if-exists`, runs
migrations, and restarts services. Use the same `ENCRYPTION_KEY` as when the backup was taken.

## Point-in-time recovery (optional)

For RPO below 24 h, enable WAL archiving on PostgreSQL (e.g. with `wal-g` or a managed database with PITR).
Managed PostgreSQL (RDS, Cloud SQL, Neon, Supabase) is a good choice in production; set `DATABASE_URL`
and remove the `postgres` service.

## Recovery drills

Quarterly: restore the latest dump into a scratch environment and run
`docker compose run --rm api python -c "from app.core.db import SessionLocal; from app.models import Company; print(SessionLocal().query(Company).count())"`.

## Disaster scenarios

| Scenario | Action |
|---|---|
| Worker crash mid-job | Automatic: job re-queued by `recover_stale_jobs`; mailbox drafts are idempotent (no duplicates). |
| Redis lost | Restart Redis; queued jobs are re-dispatched from PostgreSQL by recovery within ~10 minutes. |
| Database corruption / lost volume | Restore latest dump; re-run discovery if needed (dedupe prevents duplicates). |
| Lost `ENCRYPTION_KEY` | Restore works, but re-enter LLM/search API keys and reconnect mailboxes and connectors. |
| Leaked `SECRET_KEY` | Rotate it — all sessions are invalidated; users sign in again. |
