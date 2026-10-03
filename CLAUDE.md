# Claude Code Configuration

This file tells Claude Code how to work in this repository. The specs in `specs/` are the source
of truth for how each part behaves. If this file and a spec disagree, the spec wins, and this file
should be fixed.

## Project overview

**Yatra AI** is a multi-agent travel planner. A FastAPI service runs a LangGraph workflow, streams
its progress as Server-Sent Events, pauses for a human decision, and stores everything in
PostgreSQL. A Next.js frontend sits in front of it.

**What is built (see `README.md` and `specs/00-overview.spec.md`):**

- A 9-node LangGraph graph: `supervisor`, `flight`, `hotel`, `weather`, `budget`, `itinerary`,
  `human_approval`, `revise`, `final_response`. There is no eval node.
- The supervisor makes one LLM call that does the input guardrail, the routing and the
  constraint extraction. It fails closed, and it treats the user text as data.
- Research workers (flight, hotel, weather) run in parallel. Their tools run as MCP servers
  (child processes over stdio, through `langchain-mcp-adapters`). If a server cannot start or a
  call fails, the same tool runs in-process, and the result is tagged with `via`.
- Human-in-the-loop is real: `interrupt()` pauses the run after the first draft, and
  `Command(resume={"approved": bool, "feedback": str})` continues it. A rejection with feedback
  revises the plan, up to `MAX_REVISIONS` (default 3) times.
- State is checkpointed in PostgreSQL (`AsyncPostgresSaver`), so a paused trip survives a restart.
- The runtime model is `deepseek-flash`. If a call raises (timeout, rate limit, outage), the same
  call is retried on the fallback chain, `openai:gpt-4.1-mini` first (`LLM_FALLBACK_MODELS`).
- Two separate eval systems. `src/evals/` holds three plain LLM-as-judge functions (safety,
  factuality, budget) and a threshold gate. Nothing in the running app calls them. `evals/` at the
  repository root holds the DeepEval agent evals (15 golden tasks through the real graph), and
  `.github/scripts/eval_gate.py` is the merge gate for them. The `agent-evals` job in `ci.yml` runs both on a
  pull request or a manual run.

**What is not built (do not claim it):** real flight prices (flights are sample data), an LLM-written
first itinerary draft (it is a template), login or rate limiting, trip deletion through the API,
a live eval score (the agent evals have not completed a scored run with real API keys), a merge that is actually
blocked by the gate (that needs the repository secrets and a required status check, see
`DEPLOYMENT.md` section 11), a fallback that has been tried against real providers.

## Commands

```bash
pip install -r requirements.txt          # the app. Use requirements-eval.txt to also run the evals and the full tests
cp .env.example .env            # set DATABASE_URL and DEEPSEEK_API_KEY; OPENAI_API_KEY (fallback) and TAVILY_API_KEY are optional
docker compose up -d postgres   # or point DATABASE_URL at any PostgreSQL

python main.py                  # API on http://localhost:8000
cd frontend && npm ci && npm run dev    # UI on http://localhost:3000
```

`DATABASE_URL` is required. Everything else has a default or is optional.

### Quality checks (the same commands CI runs)

```bash
ruff check src tests evals .github/scripts
black --check src tests evals .github/scripts
pyright src
pytest tests/ -v --cov=src --cov-report=term      # needs DATABASE_URL and requirements-eval.txt
pytest tests/unit -q                              # no database needed
cd frontend && npx tsc --noEmit && npm run build
```

The last full local run (Windows, PostgreSQL 17, `requirements-eval.txt`): 394 tests passed
(357 unit and 37 integration), 91.30% coverage. On GitHub, `CI Pipeline` and `Verify` passed on commit
808083d. `agent-evals` ran once by hand and failed before scoring (a key with a trailing newline, and
2099 dates); both are fixed and no passing run is recorded yet. Without DeepEval installed,
`tests/unit/test_eval_suite.py` skips itself.

### Agent evals (need real keys, not part of the tests)

```bash
pip install -r requirements-eval.txt        # needs DEEPSEEK_API_KEY and OPENAI_API_KEY in .env
python -m evals.check_plan_judge             # does the custom judge separate good and bad plans?
python -m evals.eval_agent                   # 15 goldens through the real graph (add --limit 3 to try)
python .github/scripts/eval_gate.py          # exit 0 pass, 1 below a bar, 2 nothing trustworthy
```

Reports go to `evals/reports/` and traces to `evals/traces/`. Both are gitignored. A report from a
stub judge is a plumbing check and must never be quoted as a score. See `specs/07-evals.spec.md`,
section 8.

## Layout

| Path | What is there |
|---|---|
| `main.py` | Entry point. Sets the Windows event-loop policy, calls `load_dotenv(override=False)`, then runs uvicorn. |
| `src/api/` | `main.py` (app factory and lifespan), `streaming.py` (the shared SSE runner), `routes/` (`planning.py`, `approval.py`, `health.py`) |
| `src/agents/` | `graph.py` (the 9 nodes), `state.py`, `supervisor.py`, `routing.py`, `trip.py`, `plan.py` (plan document and statuses), `runtime.py` (graph runtime and saver wiring), `jsonutil.py` |
| `src/tools/` | `__init__.py` (the in-process tools), `gateway.py` (MCP client with in-process fallback) |
| `src/mcp_servers/` | `flights.py`, `hotels.py`, `weather.py`: the stdio MCP servers |
| `src/memory/` | `db.py` (app pool), `saver.py` (checkpoint pool and saver), `threads.py`, `migrations.py`, `migrations/*.sql` |
| `src/core/` | `config.py`, `llm.py`, `errors.py`, `telemetry.py`, `startup.py` |
| `src/evals/` | Request-time judges: `gate.py` and `judges/` (safety, factuality, budget). Not called by the running app. |
| `evals/` | DeepEval agent evals: `eval_agent.py`, `harness.py`, `slim_trace.py`, `report.py`, `check_plan_judge.py`, `judges/plan_judge.py`, `datasets/goldens.json` |
| `frontend/` | Next.js 15, React 18, TypeScript, Tailwind. The browser calls the API directly. |
| `specs/` | One spec per part (`00` to `08`, and `10-frontend`). Each ends with its known gaps. |
| `docs/` | `AUDIT.md`, `BLOCKED.md`, and `history/` (old build-night reports, not maintained) |
| `.github/workflows/` | `ci.yml` (lint, test, `agent-evals`, build) and `verify.yml` |
| `.github/scripts/eval_gate.py` | The merge gate for the agent evals. `ci.yml` calls it in the `agent-evals` job. |
| `requirements.txt`, `requirements-eval.txt` | The app (Render and Docker use this), and the app plus `deepeval` (tests and evals use this) |
| `render.yaml`, `DEPLOYMENT.md` | Render Blueprint and the deployment guide |
| `terraform/`, `infra/terraform/` | AWS Terraform from an earlier plan. Not used by the Render deployment and not reviewed here. |

## Rules for changes

1. **Read the spec first**, and update it in the same change when behaviour changes.
2. **Models are an allow-list.** Four ids are accepted: `deepseek:deepseek-flash` (the runtime
   default), `deepseek:deepseek-chat` (a legacy name that DeepSeek is retiring), `openai:gpt-4.1-mini`
   (the first fallback) and `openai:gpt-4o-mini` (the eval judge, always without fallbacks). Strings
   starting with `claude-`, `gpt-4` or `gpt-5` that are not in the list are rejected on purpose. Do
   not widen the list without being asked. A fallback with no API key is skipped with a warning and
   never raises.
3. **No side effects before `interrupt()`** in a node. The node re-runs from the top when the run
   resumes, so anything before the call would run twice.
4. **Approval must be exactly `True`.** Treat anything else as a rejection.
5. **Never echo a secret.** Error messages must not include `DATABASE_URL` or any key.
6. **Settings:** only the root `Settings` class reads `.env`. `main.py` loads it into the process
   environment so the nested sections see it. Do not remove that call (`tests/unit/test_entrypoint.py`
   pins it).
7. **Tests are deterministic.** The LLM and the network tools are faked. The real graph runs with an
   in-memory saver in unit tests and with PostgreSQL in the integration tests. `tests/unit/test_mcp_stdio.py`
   starts the real MCP servers as subprocesses.
8. **Do not invent numbers.** Test counts, coverage and latency in docs must come from a run you
   can point to.

## Common tasks

### Add a route
1. Add the handler in `src/api/routes/`.
2. Register the router in `src/api/main.py`.
3. Test it in `tests/unit/test_routes.py` (and `tests/integration/test_api.py` if it needs PostgreSQL).
4. Document it in `specs/05-api.spec.md` and the endpoint table in `DEPLOYMENT.md`.

### Add or change a graph node
1. Write the async node in `src/agents/graph.py`.
2. Register it and its edges in the graph builder. Routing decisions live in `src/agents/routing.py`.
3. Test the path in `tests/unit/test_graph_execution.py`.
4. Update `specs/02-agents.spec.md` and the diagram in `README.md`.

### Add a tool
1. Write the in-process function in `src/tools/__init__.py`.
2. Expose it from an MCP server in `src/mcp_servers/` and route it in `src/tools/gateway.py`.
3. Test the gateway fallback in `tests/unit/test_gateway.py`.

### Add a request-time eval judge (`src/evals/`)
1. Create the judge in `src/evals/judges/` and call it from `run_eval_gate()` in `src/evals/gate.py`.
2. Test it in `tests/unit/test_evals.py` with a scripted model.

### Add or change an agent eval (`evals/`)
1. For a new task, add a golden to `evals/datasets/goldens.json` (with `expect_allowed`,
   `expected_agents`, `hitl`). The gate reads the file and counts the goldens itself, but
   `tests/unit/test_eval_suite.py` pins the dataset size (15), so update that test too.
2. For a new metric, add it in `evals/eval_agent.py` with a fresh instance per task, and add its bar
   to `.github/scripts/eval_gate.py`.
3. Test it in `tests/unit/test_eval_suite.py` without a model. Update `specs/07-evals.spec.md`
   (section 8) and `specs/08-gate-ci.spec.md`.

### Add a database change
Add a new numbered file in `src/memory/migrations/`. Migrations run on every boot, so they must be
idempotent.

## Windows notes

- uvicorn 0.36 and later needs `loop="none"` plus a selector event-loop policy for psycopg.
  `main.py` already does this.
- Do not run `npx next lint`. It hangs here. Use `npm run build`.

## Deployment

The target is Render (`render.yaml`, then `DEPLOYMENT.md`). Do not create cloud resources, push
or deploy without being asked. The Docker image has not been built on the author's machine, and
the app has not been run with a real LLM, so neither the fallback chain nor the agent evals have
been seen working against a real provider.
