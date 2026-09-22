#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_PATH:=/data/watering.db}"
export DATABASE_PATH
mkdir -p "$(dirname "$DATABASE_PATH")"

# Application startup migrates the database without erasing existing records.
# One process serves the panel/API and runs sampling independently of browsers.
exec /app/.venv/bin/python backend/run.py
