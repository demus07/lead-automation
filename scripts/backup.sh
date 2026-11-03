#!/bin/sh
# PostgreSQL logical backup (custom format, compressed). Used by the `backup` compose service:
#   docker compose --profile backup run --rm backup
# Keeps the newest $KEEP backups (default 14).
set -eu
HOST="${PGHOST:-postgres}"; USER="${POSTGRES_USER:-agency}"; DB="${POSTGRES_DB:-agency}"; KEEP="${KEEP:-14}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="/backups/${DB}-${STAMP}.dump"
pg_dump -h "$HOST" -U "$USER" -d "$DB" -Fc -Z 6 -f "$OUT"
pg_restore -l "$OUT" > /dev/null   # verify the archive is readable
echo "Backup written: $OUT ($(du -h "$OUT" | cut -f1))"
ls -1t /backups/*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
