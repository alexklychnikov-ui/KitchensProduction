#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/delivery/docker-compose.postgres.yml}"
DUMP_FILE="${DUMP_FILE:-$ROOT/delivery/kitchens_bot_handover.dump}"
CONTAINER="${CONTAINER:-kitchens-postgres}"

if [[ ! -f "$DUMP_FILE" ]]; then
  echo "Dump not found: $DUMP_FILE" >&2
  exit 1
fi

cd "$ROOT"
docker compose -f "$COMPOSE_FILE" up -d

echo "Waiting for Postgres..."
for i in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U kitchens -d kitchens_bot >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker cp "$DUMP_FILE" "$CONTAINER:/tmp/kitchens_bot_handover.dump"
docker exec "$CONTAINER" pg_restore \
  -U kitchens \
  -d kitchens_bot \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  /tmp/kitchens_bot_handover.dump
docker exec "$CONTAINER" rm -f /tmp/kitchens_bot_handover.dump

echo "Database restored from $DUMP_FILE"
echo "DATABASE_URL=postgresql://kitchens:kitchens@127.0.0.1:5433/kitchens_bot"
