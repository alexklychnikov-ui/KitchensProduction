#!/bin/bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kitchens-bot}"
DUMP_PATH="${DUMP_PATH:-$APP_DIR/delivery/kitchens_bot_handover.dump}"
CONTAINER="${CONTAINER:-kitchens-postgres}"

mkdir -p "$(dirname "$DUMP_PATH")"

docker exec "$CONTAINER" pg_dump \
  -U kitchens \
  -d kitchens_bot \
  --no-owner \
  --no-acl \
  -F c \
  -f /tmp/kitchens_bot_handover.dump

docker cp "$CONTAINER:/tmp/kitchens_bot_handover.dump" "$DUMP_PATH"
docker exec "$CONTAINER" rm -f /tmp/kitchens_bot_handover.dump

ls -lh "$DUMP_PATH"
echo "Dump saved: $DUMP_PATH"
