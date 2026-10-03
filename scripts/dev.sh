#!/usr/bin/env bash
# Start API (http://localhost:8000) and web app (http://localhost:5173)
set -e
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
(cd backend && .venv/bin/uvicorn app.main:app --reload --reload-dir app --port 8000) &
API=$!
trap "kill $API 2>/dev/null" EXIT
cd frontend && npm run dev
