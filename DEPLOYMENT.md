# Yatra AI: Deployment Guide

Yatra AI is two separate programs, and they are deployed separately.

| Part | What it is | Good places to run it |
|------|------------|-----------------------|
| Frontend | Next.js 15 app in `frontend/` | Render or Vercel (or any Node host) |
| API | FastAPI + LangGraph in the repo root, needs PostgreSQL | A container host: Render (see section 5), Railway, Fly.io, Cloud Run, an EC2 box |

The API cannot run on Vercel Functions. `POST /api/plan` streams its progress as Server-Sent Events while the agents work, and that needs a long-lived process and a PostgreSQL connection pool.

The browser talks to the API directly. There is no proxy in the middle, because a proxy would buffer the stream.

```text
Browser ──► Frontend (Next.js pages, on Render or Vercel)
   │
   └──────► API container (FastAPI + LangGraph) ──► PostgreSQL
            (SSE stream)  │                         app tables + LangGraph checkpoints
                          ├─► MCP servers: flights, weather, hotels (child processes, stdio)
                          └─► DeepSeek (OpenAI gpt-4.1-mini as fallback), Tavily, Open-Meteo
```

The three MCP servers run inside the API container as child processes. They are not separate
services and need no extra port, host or deployment step.

## What has and has not been tested

- Verified locally: the API against a real PostgreSQL 17 (app tables and the LangGraph checkpointer), the three MCP servers as real child processes over stdio, the production build of the frontend, the full browser flow (plan, live progress, approval page, rejection with feedback, the three-revision cap, approve, results) with a faked LLM, and the CORS rules with `curl` and in the browser. The backend suite is 376 tests (339 unit and 37 integration) at 91.15% coverage, run on Windows against a local PostgreSQL 17. The model fallback chain and the DeepEval agent-eval suite are covered by those tests with fake clients and a stub judge.
- Not verified: a real run against the live DeepSeek or OpenAI API (the supervisor and the itinerary revision were always faked, so the fallback chain has never switched providers for real, and the wire names `deepseek-flash` and `gpt-4.1-mini` come from the providers' documentation), any live DeepEval score (no real keys were available, so the agent evals have never produced a result), the Docker image (it has never been built on this machine), Server-Sent Events through Render's free tier, and the memory use of the MCP servers on Render. The steps below for Render, Vercel and other container hosts, and the `render.yaml` Blueprint, are written from the settings the code reads and from the Render documentation. Treat your first deployment as the real test and use the checklist in section 7.
- Neither GitHub workflow had run on this version of the code when this guide was written, because it was written before the push. Look at the Actions tab for the first real result, including the new `agent-evals` job (`specs/08-gate-ci.spec.md`).
- Not deployed anywhere yet.

## 1. Environment variables

Copy `.env.example` to `.env` for local work. On a host, set these in the host's dashboard instead.

### API

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | yes | `postgresql://user:password@host:5432/dbname`. The short `postgres://` form that some hosts hand out is accepted. Managed databases usually need `?sslmode=require` at the end. |
| `DEEPSEEK_API_KEY` | yes | The default runtime model is `deepseek:deepseek-flash`. |
| `OPENAI_API_KEY` | recommended | The fallback when DeepSeek fails (`openai:gpt-4.1-mini`) and the judge in the evals. Without it, a DeepSeek outage fails the request, because the fallback is skipped with a warning. |
| `LLM_RUNTIME_MODEL` | no | Default `deepseek:deepseek-flash`. Allowed values: `deepseek:deepseek-flash`, `deepseek:deepseek-chat` (a legacy name that DeepSeek is retiring), `openai:gpt-4.1-mini`, `openai:gpt-4o-mini`. |
| `LLM_FALLBACK_MODELS` | no | Comma-separated, tried in order when the runtime model raises. Default `openai:gpt-4.1-mini,deepseek:deepseek-flash`. A model that repeats the primary, or has no API key, is skipped. Blank means no fallbacks. |
| `LLM_REQUEST_TIMEOUT` | no | Seconds one model call may take before the next model is tried. Default 45. |
| `LLM_MAX_RETRIES` | no | Retries on the same model before moving on. Default 1. Keep it low, because the fallback is the retry. |
| `TAVILY_API_KEY` | no | Hotel search. Without it, the hotels MCP server is not started, the Hotels section says search is not configured, and the rest of the plan still works. |
| `MCP_ENABLED` | no | Default `true`: flights, weather and hotels run as MCP servers (child processes). Set `false` to run the same tools in-process, which saves memory on a very small host. |
| `MCP_STARTUP_TIMEOUT` | no | Seconds to wait for each MCP server to start. Default 20. A server that is too slow is skipped and its tool runs in-process. |
| `MCP_CALL_TIMEOUT` | no | Seconds one MCP tool call may take before the in-process fallback runs. Default 25. |
| `MAX_REVISIONS` | no | How many rejections rewrite the plan before the last draft is returned unapproved. Default 3. |
| `CORS_ORIGINS` | yes, once a frontend is deployed | Comma-separated browser origins, for example `https://yatra-ai.vercel.app`. No trailing slash. The default allows only `localhost:3000`. |
| `CORS_ORIGIN_REGEX` | no | For origins that change, such as Vercel preview URLs: `https://yatra-ai-[a-z0-9-]+\.vercel\.app`. Leave empty to turn it off. |
| `APP_DEBUG` | set `false` | The default is `true`, which turns on uvicorn auto-reload. Never leave that on in a deployment. |
| `APP_ENV` | no | `production` is a label for logs. |
| `PORT` or `APP_PORT` | no | Port to listen on. `APP_PORT` wins if both are set. The default is 8000. Hosts that inject `PORT` work without extra setup. |

The API refuses to start without a reachable database. It tries 10 times, 2 seconds apart (each attempt can wait up to 15 seconds if the host is unreachable), then exits so the host can restart it. There is no separate migration step: on every start it applies its SQL migrations (`CREATE TABLE IF NOT EXISTS`, safe to repeat) and then sets up the LangGraph checkpoint tables itself. The database user therefore needs permission to create tables. Then it starts the MCP servers. A server that fails to start never stops the API; its tool falls back to the in-process version.

### Frontend

| Variable | Required | Notes |
|----------|----------|-------|
| `NEXT_PUBLIC_API_URL` | yes | Public origin of the API, no trailing slash and no path, for example `https://yatra-api.example.com`. It is baked in when the frontend is built, so changing it means redeploying the frontend. See `frontend/.env.example`. |

## 2. Run everything locally with Docker Compose

This starts PostgreSQL and the API. It does not start the frontend.

```bash
cp .env.example .env     # then set DEEPSEEK_API_KEY at least
docker compose up --build -d
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`docker compose` reads `.env` in the project folder and passes the keys to the API container. Compose sets `APP_DEBUG=false` and the database URL for you.

Then run the frontend on your machine:

```bash
cd frontend
npm install
npm run dev              # http://localhost:3000
```

Without Docker, start your own PostgreSQL, set `DATABASE_URL`, and run `python main.py` from the repo root.

On Windows, use `python main.py` (or add `--loop none` if you start uvicorn yourself). Newer uvicorn builds a loop that the PostgreSQL driver cannot use, and `main.py` already switches it.

## 3. Deploy the frontend on Vercel

1. Import the GitHub repository in Vercel.
2. Set **Root Directory** to `frontend`. Vercel detects Next.js and uses `npm run build`.
3. Under Environment Variables, add `NEXT_PUBLIC_API_URL` with your API's public URL (for Production, and for Preview if you use previews).
4. Deploy.

Do this after the API is live, because the build needs the API's URL.

## 4. Deploy the API on a container host

Any host that can run the repo's `Dockerfile` and offer a PostgreSQL database will do. The image runs `python main.py` as a non-root user.

1. Create a PostgreSQL database on the host and copy its connection string into `DATABASE_URL` (add `?sslmode=require` if the host demands TLS).
2. Create a web service from the repository using the `Dockerfile` in the root.
3. Set the environment variables from the table above. Make sure `APP_DEBUG=false`.
4. Set the health check path to `/ready`. It returns 503 until the database answers, so the host will not send traffic too early.
5. Make sure the host does not buffer or time out streamed responses early. The API already sends `X-Accel-Buffering: no` and `Cache-Control: no-cache`, which covers nginx-style proxies. A plan run makes several LLM calls and a few web requests, so keep the request timeout generous (at least a few minutes).
6. If you run behind your own reverse proxy (Caddy, nginx) on a VM, terminate HTTPS there. The browser must call the API over HTTPS when the frontend is on HTTPS.

Note on the Docker health check: the `Dockerfile` calls `http://localhost:${PORT:-8000}/health`, so it follows the injected `PORT` when there is one. A host with its own health check, such as Render, ignores it.

The application opens two connection pools per API instance: up to 20 connections for the app tables and up to 10 for the LangGraph checkpointer. That is up to 30 connections, so check your database plan's connection limit before you scale to several instances.

Each instance also starts its own set of MCP child processes. Two instances mean two sets.

## 5. Deploy everything on Render (Blueprint)

The repo has a `render.yaml` Blueprint that creates three resources in one go: a PostgreSQL database (`yatra-ai-db`), the API (`yatra-ai-api`, built from the `Dockerfile`) and the frontend (`yatra-ai-web`, a Node service built from `frontend/`). All three use the free plan and the Frankfurt region. Change `plan` and `region` in the file if you want something else.

The API and the frontend each need the other's public URL, and Render only shows a service's URL after it exists. The simplest way is to give the services the names in the Blueprint and use the predictable addresses, then check them:

1. Push the repository to GitHub.
2. In Render, choose **New > Blueprint**, connect the repository and click **Apply**. The Blueprint also sets `LLM_RUNTIME_MODEL=deepseek:deepseek-flash` and `LLM_FALLBACK_MODELS=openai:gpt-4.1-mini,deepseek:deepseek-flash` for you, and you can change both later in the dashboard without a code change. Render asks for the values marked `sync: false`:
   - `DEEPSEEK_API_KEY`: your DeepSeek key.
   - `OPENAI_API_KEY`: your OpenAI key. It is the fallback model's key. If you have none, delete the `OPENAI_API_KEY` entry from `render.yaml` before you apply the Blueprint. Do not type a fake value: a fake key makes the fallback fail with a 401 instead of being skipped.
   - `CORS_ORIGINS`: the frontend's address, `https://yatra-ai-web.onrender.com`. No trailing slash.
   - `NEXT_PUBLIC_API_URL`: the API's address, `https://yatra-ai-api.onrender.com`. No trailing slash and no path.
3. When the first deploy finishes, open both services in the dashboard and compare their real URLs with the ones you typed. Render adds a random suffix when a name is already taken, and then the address is different.
4. If either address is different, fix the variable (`CORS_ORIGINS` on the API, `NEXT_PUBLIC_API_URL` on the frontend). `NEXT_PUBLIC_API_URL` is baked in at build time, so after changing it, run **Manual Deploy > Clear build cache & deploy** on the frontend. A change to `CORS_ORIGINS` only restarts the API.
5. Optional: add `TAVILY_API_KEY` on the API service (Environment tab) to turn on real hotel search. It also lets the hotels MCP server start, so it adds one more child process (see the memory note below). It is not in the Blueprint, because Render asks for a value for every variable the file lists.
6. Run the checklist in section 7.

`autoDeployTrigger: commit` means every push to the connected branch redeploys the services. Change it to `off` in `render.yaml` if you prefer to deploy by hand.

What to expect on the free plan:

- A free web service goes to sleep after about 15 minutes without traffic and needs roughly a minute to wake up. The first request after a pause is slow, and a visitor can see a loading screen from Render.
- A free PostgreSQL database expires 30 days after it is created. Upgrade it before then, or you lose the trips stored in it. A workspace can have only one free database.
- The free web service has 512 MB of memory. This is the tightest limit for this app. The API process alone used about 107 MB after start-up in an earlier measurement, before the MCP servers existed. Each MCP server is a separate Python process, and the three that were measured used roughly 58 to 64 MB each. That adds up to about 290 MB in total. It is an estimate from a Windows machine, not a measurement on Render or on Linux, and not under load. It should fit, but it has not been confirmed. If the service restarts with out-of-memory messages in the logs, set `MCP_ENABLED=false`. The same tools then run inside the API process and the three child processes disappear.
- Whether a free service keeps a long Server-Sent Events stream open for the whole plan run (up to a few minutes) is not documented, and I did not test it. If progress stops halfway, look at the API logs first, then try a paid plan.
- Render does not use the `HEALTHCHECK` line in the `Dockerfile`. It uses `healthCheckPath: /ready` from the Blueprint, and it injects `PORT`, which the API reads. Do not set `APP_PORT` there, because it would win over `PORT`.

Python packages in `requirements.txt` are pinned to exact versions, so a Render build installs the same versions the tests ran against.

Hosting the frontend on Vercel instead: delete the `yatra-ai-web` service from `render.yaml` and follow section 3. Set `CORS_ORIGINS` on the API to the Vercel address.

## 6. Order of operations

The two sides need each other's address, so do it in this order:

1. Deploy PostgreSQL and the API. Leave `CORS_ORIGINS` at its default for now. Note the API's public URL.
2. Deploy the frontend on Vercel with `NEXT_PUBLIC_API_URL` set to that URL. Note the Vercel URL.
3. Set `CORS_ORIGINS` on the API to the Vercel URL (add `CORS_ORIGIN_REGEX` if you want preview deployments to work) and restart the API.

## 7. Checklist after deploying

Replace the example hosts with yours.

```bash
# The API is up and the database answers. /ready also reports the MCP servers
# (a server that is down is not a failure: its tool runs in-process)
curl -fsS https://YOUR-API/health
curl -fsS https://YOUR-API/ready

# CORS allows your frontend (expect an Access-Control-Allow-Origin header in the reply)
curl -i -X OPTIONS https://YOUR-API/api/plan \
  -H "Origin: https://YOUR-FRONTEND" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"

# CORS refuses a stranger (expect no Access-Control-Allow-Origin header, status 400)
curl -i -X OPTIONS https://YOUR-API/api/plan \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: POST"

# A real plan streams (needs a valid DEEPSEEK_API_KEY): you should see frames arrive one by one
curl -N -X POST https://YOUR-API/api/plan \
  -H "Content-Type: application/json" \
  -d '{"message":"Plan 4 days in Lisbon from Berlin in June, budget 1500 USD"}'
```

Then open the Vercel site and plan a trip. If the page loads but planning fails with a network error, the cause is almost always `CORS_ORIGINS` or `NEXT_PUBLIC_API_URL`.

## 8. API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | The process is alive |
| GET | `/ready` | The database answers (503 if not). Also reports the MCP server status, which is informational. |
| POST | `/api/plan` | Plan a trip, streamed as SSE: `thread`, `progress`, `plan`, `approval_required`, `done`, or `error`. The run pauses after the first draft and waits for a decision. |
| GET | `/api/threads/{thread_id}` | Messages, plan and approval state of a trip (404 if unknown) |
| PUT | `/api/threads/{thread_id}/approve` | Answer the paused plan with `{"approved": true}` or `{"approved": false, "feedback": "..."}`. It resumes the run and streams SSE again. 400 for a rejection without feedback, 404 for an unknown trip, 409 when no plan is waiting. |

The full contract, with every status code and event, is in `specs/05-api.spec.md`.

## 9. Known limits (as of this version)

- The weather, flights and hotels tools run as MCP servers (child processes of the API, over stdio). If a server cannot start or a call fails or times out, the same tool runs in-process and the result says which path answered. This keeps the app working, and it also means a broken MCP server is quiet: look at `/ready` and the logs.
- Flights are sample data, labelled `"source": "mock"` in the plan. They live behind a real MCP server, but the prices are not real.
- The first itinerary draft is built from a template and uses no LLM. Hotel neighbourhood names are a fixed list. Only a revision after a rejection is written by the LLM. Hotel results come from a Tavily search when a key is set.
- The budget split across categories is a rule of thumb. Only the flight check compares real numbers to your budget.
- Human approval is real: the run pauses with LangGraph `interrupt()`, its state is stored in PostgreSQL, and a rejection with feedback revises the plan, up to `MAX_REVISIONS` times. The pause survives an API restart. There is no timeout on a pause, so an unanswered trip stays open.
- A run in flight is tracked in memory, per process. Run one API instance, or the guard against two runs on the same trip will not hold.
- Nothing deletes a trip through the API. Old trips and their checkpoints stay in the database.
- There is no login. A `user_id` is just a label sent by the client, and the trip id is the only secret.
- There is no rate limiting. Every plan costs real LLM calls, so put a limit in front of a public deployment.
- Logs are JSON on stdout. Request trace ids are not yet set for each request, so `trace_id` is empty in most lines.
- The model fallback chain only covers a call that raises (timeout, rate limit, outage, bad key). It does not catch a reply that is wrong. With the defaults, one dead provider can add up to about 90 seconds to a request (45 seconds timeout, one retry) before the fallback answers. It has been tested with fake clients and not with real providers.
- The DeepEval agent evals (`evals/`) and the gate script (`.github/scripts/eval_gate.py`) are built, unit tested without a model and wired into the `agent-evals` CI job (section 11). No score from a real judge model exists yet, and the 0.7 and 80% bars are starting values, not measured ones (`specs/07-evals.spec.md`, `specs/08-gate-ci.spec.md`).

## 10. Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| API exits right after start with "Could not connect to the database" | Wrong `DATABASE_URL`, database not reachable from the host, or TLS needed (`?sslmode=require`) |
| `/ready` returns 503 | The database connection dropped or never opened. Check the API logs. |
| Browser console shows a CORS error | `CORS_ORIGINS` does not contain the exact frontend origin (scheme and host, no trailing slash) |
| The frontend calls `localhost:8000` in production | `NEXT_PUBLIC_API_URL` was not set at build time. Set it and redeploy. |
| Progress arrives all at once at the end | A proxy is buffering the stream. Turn buffering off for `/api/plan`. |
| "We could not plan this trip right now" | Every model in the chain failed. Check `DEEPSEEK_API_KEY`, `OPENAI_API_KEY` and the API logs (a skipped fallback is logged as a warning). |
| Log line "Skipping fallback model ...: no API key configured" | `OPENAI_API_KEY` is not set, so there is no fallback. Add it, or ignore the warning if you want DeepSeek only. |
| "This trip has no plan waiting for approval" (HTTP 409) | The plan was already answered, or a run on that trip is still going. Reload the trip. |
| The service restarts, and the logs show out-of-memory kills | The MCP child processes push the API past the plan's memory limit. Set `MCP_ENABLED=false`, or use a larger plan. |
| `/ready` shows an MCP server as `skipped` or `failed` | Skipped is normal for hotels when `TAVILY_API_KEY` is not set. For a failure, read the API logs. The tool still works in-process. |
| Auto-reload messages in production logs | `APP_DEBUG` is still `true` |

## 11. Agent evals in CI (GitHub secrets)

The `agent-evals` job in `.github/workflows/ci.yml` runs `python -m evals.eval_agent` (15 golden
tasks through the real graph, scored with DeepEval) and then `.github/scripts/eval_gate.py`. It
is separate from the Render deployment: Render does not run it and does not need DeepEval.

| What | Detail |
|---|---|
| When it runs | On a pull request to `main` or `develop`, and on a manual run (Actions tab, "Run workflow"). Not on a plain push, because it costs money. |
| Secrets | Add `DEEPSEEK_API_KEY` and `OPENAI_API_KEY` under Settings, Secrets and variables, Actions. The job needs both. |
| Without the secrets | The job writes a notice and finishes green after scoring nothing. A pull request from a fork has no secrets, so it always takes this path. |
| Blocking a merge | Add `agent-evals` as a required status check in the branch protection rules for `main`. That is a GitHub setting and not a file in the repository. |
| Run it locally | `pip install -r requirements-eval.txt`, set both keys in `.env`, then `python -m evals.check_plan_judge`, `python -m evals.eval_agent` and `python .github/scripts/eval_gate.py`. Reports go to `evals/reports/` (gitignored). |
| Gate exit codes | 0 passed, 1 a score is below its bar, 2 nothing trustworthy to judge (no summary, a stub-judge summary, or an incomplete run). |

Do the first run by hand and read the report before you make the job a required check, because no
baseline exists yet.

## 12. Cleanup

```bash
docker compose down       # stop
docker compose down -v    # stop and delete the local database volume
```
