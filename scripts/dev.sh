#!/usr/bin/env bash
# EvacuateSim developer script (bash, Linux/macOS/Git Bash).
#   ./scripts/dev.sh           setup + run backend & frontend dev servers
#   ./scripts/dev.sh --test    run all checks (pytest, ruff, vitest)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== EvacuateSim dev setup ($ROOT) ==="

if [ ! -x ".venv/bin/python" ] && [ ! -x ".venv/Scripts/python.exe" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
PY="$( [ -x ".venv/bin/python" ] && echo .venv/bin/python || echo .venv/Scripts/python.exe )"

echo "Installing backend dependencies..."
"$PY" -m pip install --quiet fastapi "uvicorn[standard]" "pydantic==2.12.5" pydantic-settings sqlalchemy numpy pytest httpx ruff

if [ ! -d "frontend/node_modules" ]; then
  echo "Installing frontend dependencies (npm)..."
  (cd frontend && npm install --no-audit --no-fund)
fi

if [ "${1:-}" = "--test" ]; then
  echo "=== Backend tests ==="
  (cd backend && ../"$PY" -m pytest tests/ && ../"$PY" -m ruff check app tests)
  echo "=== Frontend tests ==="
  (cd frontend && npm test)
  echo "All checks passed."
  exit 0
fi

echo "Starting backend on http://127.0.0.1:8000 ..."
(cd backend && "$ROOT/$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

echo "Starting frontend dev server on http://localhost:5173 ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT
echo "Backend:  http://127.0.0.1:8000 (docs: /docs)"
echo "Frontend: http://localhost:5173"
wait
