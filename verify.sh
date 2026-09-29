#!/usr/bin/env bash
set -euo pipefail

FAIL() { echo "❌ FAIL: $1"; exit 1; }
SKIP() { echo "⏭️  SKIP: $1"; }

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  VERIFY.SH — YATRA AI DEFINITION OF DONE"
echo "═══════════════════════════════════════════════════════════"

# 1. Docker build
echo "[1/7] Docker build..."
if command -v docker >/dev/null 2>&1; then
  docker compose build || FAIL "docker compose build failed"
else
  FAIL "Docker unavailable — required for verification"
fi

# 2. Docker up
echo "[2/7] Starting containers..."
docker compose up -d || FAIL "docker compose up failed"
sleep 20

# 3. Health check
echo "[3/7] Health check..."
curl -fsS http://localhost:8000/health || {
  docker compose logs --tail=100
  FAIL "/health did not return 200"
}

# 4. Readiness check
echo "[4/7] Readiness check..."
curl -fsS http://localhost:8000/ready || {
  docker compose logs --tail=100
  FAIL "/ready did not return 200"
}

# 5. Docker down
echo "[5/7] Shutting down containers..."
docker compose down >/dev/null 2>&1 || FAIL "docker compose down failed"

# 6. Unit tests
echo "[6/7] Running unit tests..."
python -m pip install -q -r requirements.txt 2>&1 | grep -v "already satisfied" || true
pytest tests/unit -q --tb=short || FAIL "unit tests failed"

# 7. Frontend build
echo "[7/7] Frontend build..."
[ -d frontend ] || FAIL "frontend/ directory missing"
(
  cd frontend
  npm install --silent
  npm run build
) || FAIL "frontend build failed"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ ALL CHECKS PASSED"
echo "═══════════════════════════════════════════════════════════"
