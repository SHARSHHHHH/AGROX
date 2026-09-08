#!/usr/bin/env bash
# Starts backend and frontend on MATCHING ports.
#
# The most common failure is a port mismatch between uvicorn and the Vite
# proxy, which shows up as ECONNREFUSED and blank dashboard cards.
set -e
cd "$(dirname "$0")"

PORT=8000
if lsof -i ":$PORT" >/dev/null 2>&1; then
  echo "  Port $PORT is busy. Using 8080 instead."
  PORT=8080
fi

echo "  Backend  : http://127.0.0.1:$PORT"
echo "  Frontend : http://127.0.0.1:5173"

echo "VITE_API_PORT=$PORT" > frontend/.env.local

( cd backend && uvicorn app.main:app --reload --port "$PORT" ) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT

echo "Waiting for the backend..."
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done

( cd frontend && npm run dev )
