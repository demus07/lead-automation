#!/bin/sh
# Restore a backup into the compose database. DESTRUCTIVE: replaces current data.
#   ./scripts/restore.sh backups/agency-20260101T000000Z.dump
set -eu
FILE="${1:?usage: restore.sh <dumpfile>}"
[ -f "$FILE" ] || { echo "No such file: $FILE"; exit 1; }
printf "This will REPLACE the current database with %s. Type 'restore' to continue: " "$FILE"
read -r ans; [ "$ans" = "restore" ] || { echo "Aborted"; exit 1; }
docker compose stop api worker beat
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$FILE"
docker compose run --rm api alembic upgrade head
docker compose start api worker beat
echo "Restore complete."
