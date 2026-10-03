#!/usr/bin/env bash
# One-time setup for local development (macOS / Linux)
set -e
cd "$(dirname "$0")/.."
command -v java >/dev/null || echo "⚠  JDK 17+ not found — Java projects cannot be analysed until it is installed."
command -v node >/dev/null || { echo "✖ Node.js 18+ is required"; exit 1; }
echo "→ Python environment"
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip >/dev/null
backend/.venv/bin/pip install -r backend/requirements.txt
echo "→ JS/TS analyzer (TypeScript compiler)"
(cd backend/analyzers/js && npm install --no-audit --no-fund)
echo "→ Web app"
(cd frontend && npm install --no-audit --no-fund)
# The ShopVerse demo history is generated automatically when the sample is imported.
[ -f .env ] || cp .env.example .env
echo "✓ Setup complete. Run ./scripts/dev.sh"
