#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_PATH:=/data/watering.db}"
: "${API_BASE:=http://localhost:5000}"

mkdir -p "$(dirname "$DATABASE_PATH")"

if [[ ! -f "$DATABASE_PATH" ]]; then
  echo "Initializing database at $DATABASE_PATH"
  uv run flask --app backend/run.py init-db
fi

printf 'window.__API_BASE__ = "%s";\n' "$API_BASE" > /app/frontend/config.js

uv run python backend/run.py &
backend_pid=$!

uv run python -m http.server 8080 --directory /app/frontend

wait "$backend_pid"
