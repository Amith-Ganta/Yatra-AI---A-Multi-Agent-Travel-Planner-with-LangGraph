# Action Required — Add 3 Secrets to GitHub

GitHub CLI (`gh`) is not available in this cloud session. The secrets must be added manually via the GitHub web interface.

## How to Add Secrets

1. **Open the Secrets settings page:**
   ```
   https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/settings/secrets/actions
   ```

2. **Click "New repository secret" and add three secrets:**

   ### Secret 1: DEEPSEEK_API_KEY
   - **Name**: `DEEPSEEK_API_KEY`
   - **Value**: Copy from your `.env` file (do NOT paste into chat)
   - Click "Add secret"

   ### Secret 2: OPENAI_API_KEY
   - **Name**: `OPENAI_API_KEY`
   - **Value**: Copy from your `.env` file
   - Click "Add secret"

   ### Secret 3: TAVILY_API_KEY
   - **Name**: `TAVILY_API_KEY`
   - **Value**: Copy from your `.env` file (optional, for web search)
   - Click "Add secret"

## Trigger the CI Workflow

After adding all three secrets:

**Option A: Automatic (recommended)**
- The workflow will trigger automatically on the next push to main
- Push a trivial commit:
  ```bash
  git commit --allow-empty -m "trigger: run CI verification"
  git push origin main
  ```

**Option B: Manual trigger**
- Go to the Actions tab: https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/actions
- Click on "Verify" workflow on the left
- Click "Run workflow" (blue button)
- Select `main` branch
- Click "Run workflow"

## Monitor the CI Run

1. Go to Actions tab: https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/actions
2. Click the running workflow (it should be the latest)
3. Watch the progress:
   - **Tier 1 (Docker build)**: Building image...
   - **Tier 1 (Docker up)**: Starting containers...
   - **Tier 1 (/health check)**: Verifying API is up...
   - **Tier 2 (unit tests)**: Running 70 tests...
   - **Tier 3 (frontend build)**: Building Next.js app...

## Expected Results

- ✅ **Tier 1 should PASS** — Docker builds and /health responds (this is the key verification)
- ✅ **Tier 2 should PASS** — 70 unit tests pass
- ⚠️ **Tier 3 may FAIL** — Frontend has TypeScript error (not critical, needs frontend developer review)

## If a Step Fails

1. Click the failed step to see the log
2. Report the error message here or in a GitHub issue
3. The error will guide the fix needed

## Timeline

- Setup secrets: ~2 minutes
- CI run time: ~10-15 minutes total
  - Docker build: 3-5 min
  - Container startup + health checks: 2 min
  - Unit tests: 1 min
  - Frontend build: 3-5 min

---

**Status**: Awaiting user action to add secrets and trigger CI  
**Documentation**: See docs/CI_RESULT.md after workflow completes
