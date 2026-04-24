#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=3000

cleanup() {
    echo ""
    echo "Stopping services..."
    kill $(jobs -p) 2>/dev/null || true
    lsof -ti tcp:$BACKEND_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
    lsof -ti tcp:$FRONTEND_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

# Kill stale processes on target ports
lsof -ti tcp:$BACKEND_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti tcp:$FRONTEND_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true

# Install dependencies
echo "Installing dependencies..."
cd "$ROOT_DIR" && uv sync

# Start backend
echo "Starting backend on http://127.0.0.1:$BACKEND_PORT ..."
(cd "$ROOT_DIR/backend" && uv run uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT --reload) &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on http://127.0.0.1:$FRONTEND_PORT ..."
(cd "$ROOT_DIR/frontend" && uv run python3 -m http.server $FRONTEND_PORT --bind 127.0.0.1) &
FRONTEND_PID=$!

echo ""
echo "========================================="
echo "  ClawSeries is running!"
echo "  Frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "  Backend:  http://127.0.0.1:$BACKEND_PORT"
echo "  API Docs: http://127.0.0.1:$BACKEND_PORT/docs"
echo "========================================="
echo "Press Ctrl+C to stop all services."
echo ""

wait
