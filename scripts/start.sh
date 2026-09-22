#!/usr/bin/env bash
# Production entrypoint for Allin1.
#
# Honours the $PORT variable that Render, Railway, Fly.io, Heroku and most
# container platforms inject, falling back to 8000 for local/Docker use.
set -euo pipefail

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WEB_CONCURRENCY:-1}"

echo "==> Starting Allin1 on ${HOST}:${PORT} (workers=${WORKERS})"
echo "==> Data directory: ${ALLIN1_DATA_DIR:-<repo>/data}"

# A single worker is intentional: download jobs are tracked in an in-process
# registry plus SQLite, so multiple workers would not share job state.
exec uvicorn backend.app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers "$WORKERS" \
  --proxy-headers \
  --forwarded-allow-ips '*'
