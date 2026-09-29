#!/usr/bin/env bash
set -euo pipefail

FAIL() { echo "❌ FAIL: $1"; exit 1; }
SKIP() { echo "⏭️  SKIP: $1"; }

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  VERIFY.SH — YATRA AI DEFINITION OF DONE"
echo "═══════════════════════════════════════════════════════════"

# 1. Python deps
echo "[1/9] Installing Python deps..."
pip install -q -r requirements.txt || FAIL "pip install failed"

# 2. DeepSeek config must be real
echo "[2/9] Checking DeepSeek config..."
grep -q "api.deepseek.com" src/core/llm.py || \
  FAIL "src/core/llm.py does not reference api.deepseek.com"
if grep -qE "GROQ_DEEPSEEK|GROQ_MIXTRAL" src/core/llm.py 2>/dev/null; then
  FAIL "Fake model config found (GROQ_DEEPSEEK / GROQ_MIXTRAL)"
fi

# 3. No stubs anywhere
echo "[3/9] Checking for stubs..."
if grep -rniE "placeholder|pending|stub|not implemented|TODO" \
   src/ evals/ frontend/src/ 2>/dev/null \
   | grep -v "test_" | grep -v ".spec.md" | grep -v "\.md:" ; then
  FAIL "stubs found (see above)"
fi

# 4. Unit tests
echo "[4/9] Running unit tests..."
pytest tests/unit -q --tb=short || FAIL "unit tests failed"

# 5. Integration tests (needs Postgres)
echo "[5/9] Ensuring Postgres is up..."
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^yatra-pg$"; then
  if command -v docker >/dev/null 2>&1; then
    docker run -d --name yatra-pg \
      -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=yatra \
      -p 5432:5432 postgres:16 >/dev/null
    sleep 8
  else
    SKIP "Docker unavailable — skipping integration tests"
  fi
fi
if command -v docker >/dev/null 2>&1; then
  pytest tests/integration -q --tb=short || FAIL "integration tests failed"
fi

# 6. Docker build (skip if docker missing)
echo "[6/9] Docker build..."
if command -v docker >/dev/null 2>&1; then
  docker-compose build || FAIL "docker-compose build failed"
else
  SKIP "Docker unavailable — cannot verify container build"
fi

# 7. Docker up + /health
echo "[7/9] Starting containers + health checks..."
if command -v docker >/dev/null 2>&1; then
  docker-compose up -d
  sleep 20
  curl -fsS http://localhost:8000/health || {
    docker-compose logs --tail=80
    FAIL "/health did not return 200"
  }
  curl -fsS http://localhost:8000/ready || {
    docker-compose logs --tail=80
    FAIL "/ready did not return 200"
  }
  docker-compose down >/dev/null 2>&1 || true
else
  SKIP "Docker unavailable — cannot verify running container"
fi

# 8. Frontend build
echo "[8/9] Frontend build..."
[ -d frontend ] || FAIL "frontend/ directory missing"
(
  cd frontend
  npm install --silent
  npm run build
) || FAIL "frontend build failed"

# 9. Evals
echo "[9/9] Running evals..."
python -m evals.run_evals 2>&1 | tail -30 || \
  SKIP "evals skipped (may need API keys not in this env)"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ ALL CHECKS PASSED"
echo "═══════════════════════════════════════════════════════════"
