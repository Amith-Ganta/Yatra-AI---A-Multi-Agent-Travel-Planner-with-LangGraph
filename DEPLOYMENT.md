# Yatra AI: Deployment Guide

Yatra AI has two front ends. The Next.js app talks to a FastAPI server, and the two are deployed
separately. The Streamlit app is one program with no server and no database, and it is the
simplest way to put the planner online (section 13).

| Part | What it is | Good places to run it |
|------|------------|-----------------------|
| Streamlit app | `streamlit_app.py` and `src/ui/`; runs the LangGraph in the same process, plans kept in memory | Streamlit Community Cloud (section 13), or `streamlit run streamlit_app.py` anywhere |
| Frontend | Next.js 15 app in `frontend/` | Render or Vercel (or any Node host) |
| API | FastAPI + LangGraph in the repo root, needs PostgreSQL | A container host: Render (see section 5), Railway, Fly.io, Cloud Run, an EC2 box |

The rest of this guide, apart from section 13, is about the Next.js app and the API.

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

- Verified locally: the API against a real PostgreSQL 17 (app tables and the LangGraph checkpointer), the three MCP servers as real child processes over stdio, the production build of the frontend, the full browser flow (plan, live progress, approval page, rejection with feedback, the three-revision cap, approve, results) with a faked LLM, and the CORS rules with `curl` and in the browser. The backend suite is 397 tests (360 unit and 37 integration) at 91.30% coverage, run on Windows against a local PostgreSQL 17. The model fallback chain and the DeepEval agent-eval suite are covered by those tests with fake clients and a stub judge.
- Not verified: a real run of the app in a browser against the live DeepSeek or OpenAI API (only the eval runs made live model calls, and their logs do not show which model answered, so the fallback chain has never been seen switching providers, and the wire names `deepseek-flash` and `gpt-4.1-mini` come from the providers' documentation), the Docker image (it has never been built on this machine), Server-Sent Events through Render's free tier, and the memory use of the MCP servers on Render. The steps below for Render, Vercel and other container hosts, and the `render.yaml` Blueprint, are written from the settings the code reads and from the Render documentation. Treat your first deployment as the real test and use the checklist in section 7.
- On GitHub, `CI Pipeline` (lint, tests, Docker build) and `Verify` passed on commit 07a4dc0. The `agent-evals` job ran three times by hand: the first run failed before scoring, the second produced real scores but failed the original gate, and the third (run 37143852885, commit 07a4dc0) passed the revised gate (see section 11). Look at the Actions tab for the latest result (`specs/08-gate-ci.spec.md`).
- The Streamlit app has 95 tests of its own: the text and table helpers, the secrets and environment set-up, the planner runtime (a real graph on a real background event loop, with the LLM and the tools faked: approval pause, revisions, the revision limit, a refused request, a failing run, a timeout), and the page itself, driven with Streamlit's `AppTest` against a fake runtime. I also ran it in a browser with a stub LLM: the trip form and the free-text box, live progress, the draft plan, approve, three revisions, the revision-limit message, an off-topic request, and the Ctrl+Enter case. Not verified for the Streamlit app: a run on Streamlit Community Cloud, a run with real DeepSeek or OpenAI keys, the MCP servers and their memory use on Community Cloud, and anything that survives a restart (plans are kept in memory only).
- Not deployed anywhere yet. An attempt to run the API on Render (section 5) did not come up, and I did not find the cause, so treat section 5 as untested. The Streamlit app has not been deployed either.

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

The repo has a `render.yaml` Blueprint that creates two services in one go: the API (`yatra-ai-api`, built from the `Dockerfile`) and the frontend (`yatra-ai-web`, a Node service built from `frontend/`). Both use the free plan and the Virginia region. The Blueprint does **not** create a database. It reuses the PostgreSQL instance that already exists in the workspace (`Yatra-Agent`, Virginia), because Render allows only one free database per workspace and a second one is refused. The services have to be in the same region as that database, because its Internal Database URL only works inside one region. If you want the Blueprint to create its own database instead, add a `databases:` block (`name`, `plan`, `region`, `databaseName`, `user`) and set `DATABASE_URL` to `fromDatabase` with `property: connectionString`, and use the same region everywhere.

The API and the frontend each need the other's public URL, and Render only shows a service's URL after it exists. The simplest way is to give the services the names in the Blueprint and use the predictable addresses, then check them:

1. Push the repository to GitHub.
2. In Render, choose **New > Blueprint**, connect the repository and click **Apply**. The Blueprint also sets `LLM_RUNTIME_MODEL=deepseek:deepseek-flash` and `LLM_FALLBACK_MODELS=openai:gpt-4.1-mini,deepseek:deepseek-flash` for you, and you can change both later in the dashboard without a code change. Render asks for the values marked `sync: false`:
   - `DATABASE_URL`: the **Internal Database URL** of the `Yatra-Agent` database. Open the database in the dashboard, go to **Connections** and copy the Internal Database URL. The API accepts `postgres://` and `postgresql://`. The app was tested on PostgreSQL 15 and 17, and this instance is PostgreSQL 18, which has not been tried. `/ready` answers 503 until the database responds, so a problem shows up there first. The Internal URL (host name without a domain, like `dpg-...-a`) only resolves for services in the same region, workspace and project environment as the database. If the API deploy fails and the log says `failed to resolve host`, the database is not on the private network of this service. Open the API service, go to **Environment**, replace `DATABASE_URL` with the **External Database URL** of the same database (the host ends in `.virginia-postgres.render.com`), save, and run **Manual Deploy > Deploy latest commit**. The External URL works from anywhere over TLS. It was tested from a laptop against this database, including the migrations.
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
- A free PostgreSQL database expires 30 days after it is created. Check the plan and the creation date of `Yatra-Agent` on its Info page, and upgrade it before the expiry date, or you lose the trips stored in it. A workspace can have only one free database.
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
- The model fallback chain only covers a call that raises (timeout, rate limit, outage, bad key). It does not catch a reply that is wrong. With the defaults, one dead provider can add up to about 90 seconds to a request (45 seconds timeout, one retry) before the fallback answers. It is unit tested with fake clients. The live eval runs made real model calls through it, but the logs do not show which model answered, so a switch to the fallback has not been observed.
- The DeepEval agent evals (`evals/`) and the gate script (`.github/scripts/eval_gate.py`) are built, unit tested without a model and wired into the `agent-evals` CI job (section 11). Two scored runs exist (3 Oct 2026). The first failed the original gate, so one golden was relabelled and two DeepEval plan metrics were made report only. The second passed the revised gate. The remaining bars (0.7 and 80%) were set before the first run, and the pass is a single run, so the spread between runs is unknown (`specs/07-evals.spec.md`, `specs/08-gate-ci.spec.md`).

## 10. Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| API exits right after start with "Could not connect to the database" | Wrong `DATABASE_URL`, database not reachable from the host, or TLS needed (`?sslmode=require`). The message names the host that was tried (never the user or the password). On Render, a host without a domain (`dpg-...-a`) is the Internal URL and only works inside the same region, workspace and environment: use the External URL instead. |
| Public API address never answers and the deploy shows "Failed deploy" | The API only opens its port after start-up succeeds. While it retries the database (about 3 minutes) the address hangs, then the process exits. Read the **Logs** tab of the failed deploy and look for "Database not reachable (attempt n/10)". |
| `/ready` returns 503 | The database connection dropped or never opened. Check the API logs. |
| Browser console shows a CORS error | `CORS_ORIGINS` does not contain the exact frontend origin (scheme and host, no trailing slash) |
| The frontend calls `localhost:8000` in production | `NEXT_PUBLIC_API_URL` was not set at build time. Set it and redeploy. |
| Progress arrives all at once at the end | A proxy is buffering the stream. Turn buffering off for `/api/plan`. |
| "We could not plan this trip right now" | Every model in the chain failed. Check `DEEPSEEK_API_KEY`, `OPENAI_API_KEY` and the API logs (a skipped fallback is logged as a warning). |
| `Illegal header value` in the logs or in an eval report | An API key was pasted with a trailing space or line break. The app strips whitespace from `DEEPSEEK_API_KEY`, `OPENAI_API_KEY` and `TAVILY_API_KEY` at start-up, so use the latest commit. On an older build, enter the key again with nothing after it. |
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
| Trip dates | The goldens write dates as `{d+N}` (N days from today), so the trips are always in the future. The supervisor knows today's date and refuses past or unrealistic dates. Set `EVAL_TODAY=YYYY-MM-DD` to pin the day for a repeatable run. |
| Pasted secrets | A secret saved with a trailing newline used to fail with `Illegal header value`. The code now strips whitespace from the key variables, and the `Check for API keys` step prints a warning (never the value) when it sees whitespace. |

Read the report before you make the job a required check. The first live run (3 Oct 2026) failed the
original gate: Guardrail 14 of 15, Routing 10 of 11, Approval Loop 10 of 11, Task Completion 0.87,
DeepEval Plan Quality 0.55 and Plan Adherence 0.16, custom Plan Quality 0.95. The Tokyo $500 golden was
relabelled as a refusal and the two DeepEval plan metrics became report only (my call, see
`specs/07-evals.spec.md`, section 8.3). The second run (run 37143852885, commit `07a4dc0`) passed the
revised gate: Guardrail 15 of 15, Routing 10 of 10, Approval Loop 10 of 10, Task Completion 0.965,
custom Plan Quality 0.976, and the two DeepEval plan metrics at 0.50 and 0.05, reported only. That is one
run on a gate I revised after the first, so watch a few more runs before you make the job a required
check. Render does not read GitHub secrets, so none of this blocks a deployment.

## 12. Cleanup

```bash
docker compose down       # stop
docker compose down -v    # stop and delete the local database volume
```

## 13. Streamlit Community Cloud

The Streamlit app (`streamlit_app.py`, code in `src/ui/`) needs no database, no API server and no
Docker. It runs the same LangGraph as the API inside the Streamlit process, so the supervisor
guardrail, the three tools, the approval pause and the revision loop behave the same way. Plans
live in memory (`InMemorySaver`), not in PostgreSQL.

### Run it on your own machine first

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then paste your keys into it
streamlit run streamlit_app.py
```

`.streamlit/secrets.toml` is git-ignored. A `.env` file with the same names works too. A variable
that is already set in the environment wins over the secrets file.

### Deploy it (you do this in your own Streamlit account)

1. Open https://share.streamlit.io and sign in with GitHub. Allow access to the repository.
2. Choose **Create app** and deploy from a GitHub repository (the button names change from time
   to time).
3. Repository: `Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph`. Branch: `main`.
   Main file path: `streamlit_app.py`.
4. Open **Advanced settings**. Pick **Python 3.11** (the version the app was developed and tested
   on; a newer default may not suit the pinned packages). Paste the secrets below into the
   **Secrets** box.
5. Choose **Deploy**. The first build installs `requirements.txt` and takes a few minutes. Read the
   build log on the right if it fails.

Secrets (TOML). Use your own keys, and do not put them anywhere else:

```toml
DEEPSEEK_API_KEY = "your-deepseek-key"
OPENAI_API_KEY = "your-openai-key"
# TAVILY_API_KEY = "your-tavily-key"   # optional, live hotel search
# MCP_ENABLED = false                  # optional, see below
```

Do not add `DATABASE_URL`. The app sets an unused placeholder itself, because the settings class
insists on a value even though the Streamlit app never opens a connection.

Every top-level line in the Secrets box becomes an environment variable with the name in upper
case, so any variable from section 1 (`LLM_RUNTIME_MODEL`, `LLM_FALLBACK_MODELS`,
`MCP_STARTUP_TIMEOUT`, `MAX_REVISIONS` and the others) can be set there as well. The API-only
ones (`CORS_ORIGINS`, `PORT`) do nothing in this app. Secrets can be changed later under **Manage
app**, **Settings**, **Secrets**, and the app restarts.

If a model key is missing, the app says which one and does not start a plan. A missing
`OPENAI_API_KEY` is only a warning in the logs: the fallback model is skipped.

### Which dependency file Community Cloud reads

Community Cloud looks for `uv.lock`, then `Pipfile`, then `environment.yml`, then
`requirements.txt`, then `pyproject.toml`, and uses the first one it finds
([Streamlit docs, app dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)).
This repository has no `uv.lock`, `Pipfile` or `environment.yml`, so `requirements.txt` is used. The
`pyproject.toml` only holds tool settings and is never reached. Do not add one of the three
higher-priority files without checking this. `requirements.txt` also carries the API and test
packages (FastAPI, psycopg, pytest, pyright), so the build is heavier than the app needs. That
costs build time only. I have not built it on Community Cloud, so read the first build log.

### MCP servers on Community Cloud

By default the flights, weather and hotels tools start as three MCP server child processes, as in
the API. The Streamlit docs list Community Cloud limits of 690 MB minimum and 2.7 GB maximum of
memory per app (the page is dated February 2024, so check it for the current numbers). I measured
about 674 MB for the API with the MCP servers running, and Streamlit and the Python imports come
on top, so the app may sit above the guaranteed minimum and depend on spare capacity. I have not
measured the Streamlit app on Community Cloud.

The servers start one after the other, and each may take up to `MCP_STARTUP_TIMEOUT` seconds
(default 20). A server that is too slow or fails is skipped, and the same tool runs in-process,
so the plan still works. The **Tools** block in the sidebar shows what is running. If the app is
slow to start or keeps restarting, set `MCP_ENABLED = false` in the Secrets box: the tools then
run in-process and the plans are the same.

### What to expect

- **Plans are kept in memory.** A restart, a redeploy or the app going to sleep (Community Cloud
  does this after about 12 hours without visitors) loses every plan. Closing or reloading the tab
  also loses your place, because the trip id lives in the browser session. Streamlit then shows
  the start page again.
- **The first load after a sleep takes about a minute**, because the app wakes up and imports the
  graph.
- **There is no login and no rate limit.** Anyone with the link can start a plan, and every plan
  costs real LLM calls on your keys. Set a spending limit with your model providers before you
  share the link, and look at the app's Share settings in Streamlit if you want to restrict who
  can open it (I have not checked what the free tier allows).
- **Flights are sample data**, and the first itinerary draft is a template. See section 9, which
  applies here too.
- **One planner per process.** All sessions share one background event loop and one in-memory
  checkpointer, and each browser session has its own trip id.
