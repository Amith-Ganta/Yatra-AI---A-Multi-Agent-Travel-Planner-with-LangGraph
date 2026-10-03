# Yatra AI

### A multi-agent travel planner that treats the LLM as an untrusted component: guarded at the door, paused for a human before anything is final, and held to tests that run against a real database.

Built with **LangGraph, FastAPI, PostgreSQL, MCP, Next.js and Server-Sent Events**. Specified first, built spec by spec, then reviewed against its own claims. The defects that review found are listed below with the tests that now guard them.

---

## The 60-second version

Most "AI agent" demos prove that a model can talk. This project is about everything around the model that decides whether you can trust it:

- **A guardrail that fails closed.** Every request goes through a supervisor that returns a structured verdict. If the model errors, returns garbage, or answers `"allowed": "yes"` instead of a real boolean, the request is rejected, not waved through.
- **A real human in the loop.** After the itinerary is drafted, the graph stops at a LangGraph `interrupt()`. The paused run is saved in PostgreSQL by the `AsyncPostgresSaver` checkpointer, so nothing is running and nothing is lost if the server restarts. You answer later, and `Command(resume=...)` continues the same thread. Reject with feedback and the itinerary is revised, up to 3 times, then the last draft is kept and labelled as not approved.
- **Tools behind real MCP servers.** Flights, hotels and weather are three stdio MCP servers, started as subprocesses of the API and called through `langchain-mcp-adapters`. If a server cannot start or a call fails, the same tool runs in-process, and every result says which path answered (`"via": "mcp"` or `"in-process"`).
- **Parallel specialists, deterministic routing.** Flight, hotel and weather research run as one parallel wave. Budget runs after the wave, because it needs the flight price. Which specialists run is the model's choice. The order in which the graph moves is plain Python with a test that proves every node runs exactly once.
- **Two evaluation layers, both fail-safe.** Three request-time LLM judges (safety, factuality, budget) return JSON scores, and a judge that errors or has no credentials scores `0.0`, never a silent pass. A second layer, built with DeepEval after the [campusx agent-evals](https://github.com/campusx-official/agent-evals-deepeval) approach, runs 15 golden tasks through the real graph (approval loop included) and feeds a merge gate. [It has not produced a live score yet](#agent-evals-with-deepeval).
- **A model fallback chain.** The agents run on `deepseek-flash`. If a call raises (timeout, rate limit, outage), the same call is retried on OpenAI `gpt-4.1-mini`. A fallback with no API key is skipped with a warning, never an error. This is tested with fake clients only.
- **Streaming end to end.** `graph.astream` is exposed over Server-Sent Events, so the browser shows each agent finishing while the others are still working, and an `approval_required` frame when the run is waiting for you.
- **Tests that touch a real database and a real subprocess.** 394 tests pass. The 37 integration tests run against a real PostgreSQL, including one that pauses a plan, restarts the application and resumes it. Four more tests start a real MCP server over stdio instead of faking it.
- **A written audit trail.** Specs, an audit report, a blocker report, and a review that found the app could not serve a single database request even though CI was green. That story is told [below](#the-review-that-found-the-database-was-never-opened).

> **Honest scope, stated up front.** The agent graph, the guardrail, the human approval loop, the checkpointer, the MCP tool servers, the API, the memory layer and the frontend are real and verified locally. Flights are mock data (labelled `"source": "mock"` in every plan). The first draft of the itinerary is built from a template, and only the revisions after your feedback are written by the model. The eval layers are not in the request path, and the DeepEval agent evals and the model fallback have never run against a real provider, so no live eval score exists. The application has never been run in the browser against a real LLM key, the Docker image has not been built on my machine (CI builds it), and nothing is deployed yet. Every gap is listed in [What is real and what is roadmap](#what-is-real-and-what-is-roadmap). I would rather you read the gaps from me than find them yourself.

---

## Evidence at a glance

The test, coverage and lint rows were run on my Windows machine on 3 October 2026. The other rows were checked on 2 October 2026. No GitHub Actions run of this version existed when I wrote this, so the Actions tab is the live source of truth once it has run.

| Signal | Value | Proof |
|---|---|---|
| Orchestration | 9-node LangGraph `StateGraph` over a typed `TravelState`. On the approve-first-time path every node runs exactly once | [`graph.py`](src/agents/graph.py), [`test_graph_execution.py`](tests/unit/test_graph_execution.py) |
| Safety at the door | LLM guardrail with a JSON verdict. Fails closed on an error, an unparseable reply, or a non-boolean `allowed` | [`supervisor.py`](src/agents/supervisor.py), [`test_supervisor.py`](tests/unit/test_supervisor.py) |
| Human in the loop | `interrupt()` and `Command(resume=...)`. A rejection needs feedback. Revision cap of 3. A paused plan survives an application restart | [`graph.py`](src/agents/graph.py), [`approval.py`](src/api/routes/approval.py), [`test_api.py`](tests/integration/test_api.py) |
| Tools | 3 MCP servers over stdio through `langchain-mcp-adapters`, with an in-process fallback | [`src/mcp_servers/`](src/mcp_servers), [`gateway.py`](src/tools/gateway.py), [`test_mcp_stdio.py`](tests/unit/test_mcp_stdio.py) |
| Quality at the exit | 3 judges: safety, factuality, budget. Fail-safe score `0.0` | [`src/evals/`](src/evals), [`test_evals.py`](tests/unit/test_evals.py) |
| Agent evals | DeepEval 4.1.5: Task Completion, Plan Quality, Plan Adherence and a custom plan judge, plus code checks for guardrail, routing and the approval loop, over 15 golden tasks. A gate script and a CI job (`agent-evals`) are wired to it. 71 key-free tests cover the plumbing. **No live score yet** | [`evals/`](evals), [`eval_gate.py`](.github/scripts/eval_gate.py), [`test_eval_suite.py`](tests/unit/test_eval_suite.py) |
| Model fallbacks | `deepseek-flash`, then `gpt-4.1-mini` on a failure. Judges use `gpt-4o-mini` and never fall back. Tested with fake clients, not with real providers | [`llm.py`](src/core/llm.py), [`test_llm_factory.py`](tests/unit/test_llm_factory.py) |
| API | Async FastAPI, typed SSE frames, thread memory, `/ready` returns 503 until the database answers | [`src/api/routes/`](src/api/routes) |
| Persistence | PostgreSQL threads and messages, LangGraph checkpoints, pooled connections, idempotent migrations on startup, retry until the database is up | [`src/memory/`](src/memory), [`src/core/startup.py`](src/core/startup.py) |
| Frontend | Next.js 15 (App Router), React 18, Tailwind. 4 pages, 11 components, 2 SSE and thread hooks. `tsc` and `next build` are clean | [`frontend/`](frontend) |
| Tests | **394 passed**: 357 unit and 37 integration, the integration suite on a real PostgreSQL 17 with the LLM faked. Run with `requirements-eval.txt`, so the DeepEval tests are included | [`tests/`](tests) |
| Coverage | **91.30%** of `src`, measured with `pytest --cov=src`. The MCP server files show 0% because they run in a subprocess that the coverage tool does not follow | `pytest.ini` |
| Static checks | `ruff` and `black` clean on `src`, `tests`, `evals` and `.github/scripts`. `pyright` 0 errors on `src` | [`ci.yml`](.github/workflows/ci.yml) |
| Browser check | Plan, live progress stream, redirect to the approval page, an empty rejection blocked, a rejection with feedback, the "revised draft N of 3" counter, the cap at 3 ending in "revision limit", approval, and the results page with its banners and weather. Driven in a real browser against the production Next build. The LLM, the supervisor and the three network tools were faked. The graph, the SSE stream, the plan documents and the PostgreSQL checkpointer were real | see [limits](#what-is-real-and-what-is-roadmap) |
| Method | 10 spec files drive the code. A written self-audit found 11 issues in the first pass | [`specs/`](specs), [`docs/AUDIT.md`](docs/AUDIT.md) |
| History | 86 commits between 27 and 30 September 2026, before the work described here | `git log` |

If you only have two minutes, read these four files: [`graph.py`](src/agents/graph.py), [`supervisor.py`](src/agents/supervisor.py), [`gateway.py`](src/tools/gateway.py) and [`docs/BLOCKED.md`](docs/BLOCKED.md).

---

## System architecture

```mermaid
flowchart LR
    U([Traveller]) --> FE["Next.js 15<br/>frontend"]
    FE -->|"POST /api/plan<br/>PUT /api/threads/id/approve<br/>both stream SSE"| API["FastAPI<br/>async"]
    API <--> PG[("PostgreSQL<br/>threads, messages,<br/>LangGraph checkpoints")]
    API --> G["LangGraph<br/>9 nodes, human approval<br/>pauses the run"]
    G <-->|"AsyncPostgresSaver<br/>state saved at every step"| PG
    G --> LLM["LLM factory<br/>deepseek-flash for agents<br/>gpt-4.1-mini as fallback<br/>gpt-4o-mini for judges"]
    G -->|"langchain-mcp-adapters<br/>stdio"| MCP

    subgraph MCP["MCP servers: subprocesses of the API"]
        direction TB
        M1["hotels<br/>Tavily search"]
        M2["flights<br/>mock data"]
        M3["weather<br/>Open-Meteo"]
    end

    G -.->|"server down<br/>or MCP_ENABLED=false"| FB["In-process tools<br/>the same functions"]
    G -.-> EV["Eval layers<br/>not in request path"]

    classDef live fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef mock fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef planned fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    class FE,API,PG,G,LLM,M1,M3,FB live;
    class M2 mock;
    class EV planned;
```

Green is live code. Amber is mock data. Purple dashed is built and tested but not wired into the runtime path.

---

## The agent workflow

The supervisor is both the security boundary and the router. It decides whether the request is allowed and which specialists are needed. Everything after that is a fixed graph, with one place where it waits for a person.

```mermaid
%%{init: {"flowchart": {"rankSpacing": 28, "nodeSpacing": 30}}}%%
flowchart TD
    S([Start]) --> SUP["supervisor<br/>LLM guardrail returns JSON:<br/>allowed, reason, selected_agents, trip_constraints"]
    SUP -->|"allowed is not true<br/>or any error"| FIN
    SUP -->|"allowed, research selected"| WAVE
    SUP -.->|"no research selected"| B
    SUP -.->|"no research, no budget"| IT

    subgraph WAVE["Research wave: one parallel superstep"]
        direction LR
        F["flight"]
        H["hotel"]
        W["weather"]
    end

    WAVE -->|"budget selected"| B["budget<br/>needs the flight cost"]
    WAVE -.->|"budget not selected"| IT
    B --> IT["itinerary<br/>draft one: template<br/>after feedback: LLM rewrite"]
    IT --> HA{"human_approval<br/>interrupt(): the run<br/>pauses and is saved"}
    HA -->|"approved"| FIN["final_response"]
    HA -->|"rejected with feedback<br/>and revisions left"| REV["revise<br/>count plus one,<br/>clear the decision"]
    REV --> IT
    HA -->|"rejected at the cap<br/>3 revisions used"| FIN
    FIN --> E([End])

    classDef guard fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef worker fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    classDef gate fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    class SUP guard;
    class F,H,W,B worker;
    class HA,REV gate;
```

Five design choices worth naming:

1. **The model selects, the code routes.** `selected_agents` comes from the LLM, but the routing functions in [`routing.py`](src/agents/routing.py) are small pure functions. They are unit-tested without calling a model.
2. **One superstep, one next node.** Every research worker returns the same next target, so LangGraph merges them and runs budget (or itinerary) once after the whole wave. An earlier version fanned out to itinerary as well and ran everything twice. See finding F1.
3. **Rejection is a first-class path.** A refused request goes straight to `final_response` with the reason. It never touches a tool and it never pauses for approval.
4. **The approval node has no side effects before `interrupt()`.** On resume LangGraph runs the node again from its first line, so anything done before the pause would be done twice. The node only builds the question, pauses, and reads the answer.
5. **A revision changes the words, not the facts.** When you reject a draft, the model may rewrite only the activity text of each day. Day numbers, dates and the weather forecast stay as computed. If the model's reply is unusable, the previous draft is kept and the plan says that your feedback was not applied. Your feedback is passed to the model inside tags as data, not as instructions.

---

## Request lifecycle: plan, pause, approve

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as FastAPI
    participant D as PostgreSQL
    participant G as LangGraph

    B->>A: POST /api/plan with message
    A->>D: create or resume thread, store user message
    A-->>B: SSE frame thread
    A->>G: astream on this thread_id
    loop every node update
        G-->>A: node output
        A-->>B: SSE frame progress with node name
    end
    G->>D: checkpoint, then interrupt() at human_approval
    A->>D: store the draft as an assistant message
    A-->>B: SSE frames plan, approval_required, done
    Note over B,G: Paused. No process is waiting.<br/>The run lives in the Postgres checkpoint.
    B->>A: PUT /api/threads/thread_id/approve
    A->>D: record the decision as a message
    A->>G: astream Command(resume=decision)
    alt approved
        G-->>A: final_response
        A-->>B: SSE frames progress, plan, done
    else rejected with feedback, revisions left
        G-->>A: revise, itinerary, human_approval pauses again
        A-->>B: SSE frames progress, plan, approval_required, done
    end
```

The plan is saved before the `plan` frame is sent, so the results page can always reload it with `GET /api/threads/{thread_id}`. Any failure inside the stream becomes a single `error` frame with a generic message. Exception text is logged, never sent to the browser. A second run on a thread that is already running is refused, so two requests cannot resume the same checkpoint.

---

## Deployment shape

The API cannot run on Vercel Functions, because a plan streams for tens of seconds, keeps MCP subprocesses alive and needs a connection pool. So the two halves are deployed separately. The browser talks to the API directly, because a proxy in the middle would buffer the stream.

```mermaid
flowchart LR
    BR([Browser]) -->|"pages"| WEB["Frontend host<br/>Next.js<br/>NEXT_PUBLIC_API_URL set at build time"]
    BR -->|"SSE and REST<br/>CORS allowlist"| API["Container host<br/>FastAPI from the Dockerfile<br/>health check on /ready"]
    API --> PG[("Managed PostgreSQL")]
    API -->|"stdio"| MCP["3 MCP server subprocesses<br/>about 60 MB each, measured"]
    API --> EXT["DeepSeek<br/>Tavily<br/>Open-Meteo"]
    MCP --> EXT

    classDef todo fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    class WEB,API,PG,MCP todo;
```

Purple dashed means "prepared, not deployed yet". [`render.yaml`](render.yaml) is a Render Blueprint for the database, the API and the frontend, and the frontend also works on Vercel. [`DEPLOYMENT.md`](DEPLOYMENT.md) has the environment variables, the order of operations and a post-deploy checklist. Two things to know before you deploy:

- The API allows only `localhost:3000` by default, so a deployed frontend needs `CORS_ORIGINS` set.
- The three MCP servers live inside the API's container, so one small web service runs four Python processes. I measured about 60 MB for each server and estimate about 290 MB in total, which is close to the 512 MB of a free Render instance. If it restarts for lack of memory, set `MCP_ENABLED=false` and the same tools run inside the API process.

---

## How quality is enforced

Quality is checked at three places: at runtime, on every push, and after a failure.

```mermaid
flowchart LR
    subgraph RT["Runtime"]
        direction TB
        R1["Supervisor guardrail<br/>fails closed"] --> R3["Human approval<br/>nothing is final<br/>until a person says so"]
        R3 --> R2["Eval layer<br/>safety, factuality, budget<br/>judge error gives score 0.0"]
    end

    subgraph CI["Every push: two workflows"]
        direction TB
        C1["CI Pipeline<br/>ruff, black, pyright<br/>pytest with a Postgres service"] --> C3["agent-evals<br/>DeepEval and the gate<br/>pull request or manual run"]
        C1 --> C2["Verify<br/>docker build and compose up<br/>poll /ready, unit tests<br/>frontend build"]
    end

    subgraph AF["After a failure"]
        direction TB
        A1["Stop guessing<br/>write docs/BLOCKED.md<br/>symptom, attempts, unblock options"]
    end

    RT ~~~ CI
    CI ~~~ AF

    classDef ok fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef planned fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    classDef doc fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    class R1,R3,C1,C2 ok;
    class R2,C3 planned;
    class A1 doc;
```

The two workflows have different jobs. **CI Pipeline** is the strict gate: lint, types and the full test suite against a PostgreSQL service. **Verify** is the definition of done: does the container boot, does the database answer on `/ready`, do the unit tests pass, does the frontend build. On a pull request or a manual run, CI Pipeline also runs the `agent-evals` job. The dashed boxes are built and wired but have not produced a result for the real agent yet.

### Agent evals with DeepEval

`python -m evals.eval_agent` runs 15 golden tasks (11 the supervisor must allow, 4 it must refuse) through the real 9-node graph. A scripted traveller answers the approval question: approve at once, reject once with feedback, or reject until the revision cap. Each task becomes one DeepEval trace across the pause and the resume.

| Metric | Kind | Bar in the gate |
|---|---|---|
| Guardrail (allowed requests allowed, unsafe ones refused) | code, 15 tasks | all pass |
| Approval Loop (final status and revision count match the script) | code, 11 tasks | all pass |
| Routing (the expected agents ran) | code, 11 tasks | at least 80% |
| Task Completion, Plan Quality, Plan Adherence | DeepEval, 11 tasks | average at least 0.7 each |
| Plan Quality that sees trip details | custom GEval judge, 11 tasks | average at least 0.7 |

The gate (`.github/scripts/eval_gate.py`) exits 0 on a pass, 1 when a metric is below its bar, and 2 when there is nothing trustworthy to judge (no summary, a stub-judge summary, or a partial run). A task that errored counts as 0. The judge is OpenAI `gpt-4o-mini` with no fallbacks, so scores always come from the same model.

**Verified:** the wiring on the real graph and the real DeepEval iterator (with a stub judge, which is a plumbing check and not a score), the gate's three exit codes, and 71 key-free tests. The first manual run of `agent-evals` on GitHub failed before it scored anything, for two bugs that are now fixed: an API key saved with a trailing newline, and goldens with 2099 dates that the supervisor refused. **Not verified:** any live score, whether Plan Quality and Plan Adherence extract a sensible plan from a Yatra trace, whether the custom judge separates good plans from bad ones (`python -m evals.check_plan_judge`), and whether the 0.7 and 80% bars suit this agent. They are starting values, because no baseline exists. Details are in [`specs/07-evals.spec.md`](specs/07-evals.spec.md), section 8.

---

## The review that found the database was never opened

The first CI runs went green. I then re-read the code against its own claims and ran the API against a real PostgreSQL. It could not serve a single database request.

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 460, "rankSpacing": 30}}}%%
flowchart TB
    A["Runs 9 to 13: Docker /health fails<br/>and there are no container logs"] --> B["Five blind fixes, none worked<br/>autonomous loop stopped"]
    B --> C["docs/BLOCKED.md written<br/>symptom, attempts, unblock options"]
    C --> D["Root cause: API-key validation ran at startup<br/>and crashed the app before it listened"]
    D --> E["Fix: validate lazily<br/>commits 688e81c and 690aac7"]

    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef doc fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    class A,B bad;
    class C doc;
    class D,E good;
```

The lesson I took from it: a health check that does not touch the database proves the process is alive, not that the product works. `/health` stays a liveness probe. `/ready` is the one that checks the database.

### The earlier bug hunt

The first red-to-green story in the history is also worth reading, because it shows when to stop.

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 460, "rankSpacing": 30}}}%%
flowchart TB
    A["Verify was green<br/>but it only called /health"] --> B["Ran the API on a real<br/>PostgreSQL 17"]
    B --> C["Finding F0: pool never opened, migrations never run<br/>every database route returned 500"]
    C --> D["Fix: open pool on startup, retry 10 times,<br/>fail fast, idempotent migrations"]
    D --> E["Tests: test_startup.py plus the integration suite<br/>on real PostgreSQL"]
    E --> F["verify.yml now polls /ready<br/>503 until the database answers"]

    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    class A,B,C bad;
    class D,E,F good;
```

- **Stop when blind.** After five blind fixes I stopped guessing and wrote down what was known, what was tried and what would unblock it: [`docs/BLOCKED.md`](docs/BLOCKED.md).
- **Config must not take the service down.** A missing key should fail the feature that needs it, not the process. Keys are validated lazily.
- **Make failure visible.** The cloud build had no container logs, which is why the cause stayed hidden for five runs.

---

## Defects found and fixed

These came from reading the code against its claims and running it, not from a failing test. Each one now has a regression test unless the table says otherwise.

| # | Defect | Impact | Guarded by |
|---|---|---|---|
| F0 | The database pool was never opened and migrations never ran | Every route that touched the database returned 500 | [`test_startup.py`](tests/unit/test_startup.py), [`tests/integration/`](tests/integration) |
| F1 | The supervisor's router always included `itinerary` in the fan-out list | `itinerary`, `human_approval` and `final_response` each ran twice | `test_every_node_runs_exactly_once` |
| F2 | The supervisor emitted `start_date` and `budget_usd`, the workers read `departure_date` and `budget` | Workers silently fell back to defaults, so the user's dates and budget were ignored | [`test_trip.py`](tests/unit/test_trip.py) (`test_supervisor_field_names_are_mapped`), `test_workers_receive_supervisor_field_names` |
| F3 | `/ready` returned a Python tuple, which FastAPI serialised as a JSON array with HTTP 200 | "Not ready" looked like success | [`test_readiness.py`](tests/unit/test_readiness.py) |
| F4 | Results and approve pages showed hard-coded sample data | The UI did not display the real plan | Wired to `GET /api/threads/{id}`. Verified in a browser, no automated frontend test yet |
| F6 | Budget ran in the same superstep as flight | The budget was computed before the flight price existed | `test_budget_uses_real_flight_cost`, `test_budget_flags_flights_over_budget` |
| J1 | The judges called the model with the wrong shape (a class instead of an instance, a prompt type the client rejected) | None of the three judges could run | `TestJudgeRobustness` in [`test_evals.py`](tests/unit/test_evals.py): plain string prompt, fenced JSON replies, unparseable replies, missing credentials |
| S1 | The guardrail trusted whatever the model returned | `"allowed": "false"` (a string) could pass as truthy | `test_allowed_must_be_a_real_boolean` in [`test_supervisor.py`](tests/unit/test_supervisor.py) |
| W1 | uvicorn 0.36 or newer on Windows uses an event loop the async PostgreSQL driver cannot use | The API crashed on startup on Windows | `main.py` switches the loop. Windows-only, no automated test |
| C1 | CORS allowed any origin | Any website could call the API from a visitor's browser | [`test_cors.py`](tests/unit/test_cors.py) |
| D1 | `.dockerignore` matched a `.gitignore` rule, so it was never committed | Clean-clone Docker builds had no ignore rules | `.gitignore` fixed, `.dockerignore` tracked |
| N1 | Next.js 14.2.35 carried critical and high advisories | Upgrade needed before any public deploy | Upgraded to 15.5.27, `next build` and the browser flow re-verified |
| E1 | Only the root settings object read `.env`. The nested sections (MCP, database, LLM) read only real environment variables, and the MCP server subprocesses inherit only those | A key kept in `.env` worked for the API settings but was silently missing for the Tavily hotel server and for the MCP switches | `main.py` loads `.env` before the app is imported, without overriding real variables. [`test_entrypoint.py`](tests/unit/test_entrypoint.py) pins the import order and the no-override rule |

Smaller fixes landed with their own tests: hotel search through Tavily, weather through Open-Meteo (with a fallback to last year's conditions for far-future dates), the budget label wording, a stale-approval bug on re-plan, structured log fields, and `postgres://` and `PORT` handling for hosting platforms.

---

## Engineering decisions and trade-offs

| Decision | Why | Trade-off I accepted |
|---|---|---|
| Spec first, code second (`specs/00` to `10`) | A spec gives the tests and the reviewer something fixed to check against | Specs drift. Some numbers in them are targets, not measurements |
| Guardrail fails **closed** | A safety layer that fails open is decoration | Some valid requests are rejected when the guardrail model has a bad moment |
| Judges fail with score **0.0** | A broken judge must never look like a pass | A flaky judge shows up as a failing gate, which is annoying but honest |
| Parallel research wave, budget after it | Flight, hotel and weather are independent, so wall-clock time is the slowest one, not the sum. Budget needs the flight price | Needs a typed shared state and careful merge rules |
| Human approval as `interrupt()` plus a Postgres checkpoint, not a flag in a table | The run really stops and can be resumed after a restart. A stored flag would only be a record of a decision that nothing waits for | The checkpointer needs its own connection pool, and the graph must be built with it |
| A revision cap of 3 | An open-ended loop is an open-ended bill. After 3 rejections the last draft is kept and labelled as not approved | A person who wants a fourth change has to start a new request |
| Tools as MCP servers, with an in-process fallback | The tools are separate processes with their own failure and timeout, and any MCP client can use them. A server that is down does not take the plan down | Three extra processes and about 180 MB of memory. A subprocess is not counted by the coverage tool |
| MCP servers get only the keys they need | A tool process should not see the database URL or the LLM keys | Each server's environment is listed explicitly in [`gateway.py`](src/tools/gateway.py) |
| SSE rather than WebSockets | One-way streaming is all the UI needs, it works through proxies and is simple to test. The approval answer is a normal `PUT` whose response is itself a stream | No client-to-server messages on the same channel |
| Browser calls the API directly | A Next.js proxy would buffer the stream and defeat SSE | CORS must be configured per deployment |
| DeepSeek for agents, OpenAI as the fallback and for judges | The judge should not grade its own family. DeepSeek is cheap for high-volume agent calls. If it fails, the same call moves to `gpt-4.1-mini`, so a provider outage does not end the trip. Judges never fall back, so their scores stay comparable | Two providers, two keys, two failure modes. A failover can add about 90 seconds to one request in the worst case (45 second timeout, one retry). A small `LLMFactory` hides it |
| Real PostgreSQL in integration tests | Mocks would have hidden F0 | Tests need a database. CI provides one as a service |
| Template first draft, LLM only for revisions | The first draft is predictable and testable, and a revision only touches words, so the facts stay correct | The first draft is not yet "intelligent". See roadmap M4 |

---

## What is real and what is roadmap

| Capability | Status | Evidence |
|---|---|---|
| Supervisor guardrail with fail-closed JSON verdict | **Working** | [`supervisor.py`](src/agents/supervisor.py) |
| Parallel research wave, typed state, budget after research | **Working** | [`graph.py`](src/agents/graph.py), [`routing.py`](src/agents/routing.py) |
| Human approval: pause, resume, revise, cap | **Working.** Tested in unit tests (in-memory saver) and in integration tests (PostgreSQL saver), including a restart while paused | [`graph.py`](src/agents/graph.py), [`approval.py`](src/api/routes/approval.py) |
| PostgreSQL checkpointer | **Working.** `AsyncPostgresSaver` with its own connection pool | [`saver.py`](src/memory/saver.py), [`runtime.py`](src/agents/runtime.py) |
| MCP tool servers | **Working.** A real stdio server is started and called in tests. Fallback to in-process tools is tested too | [`src/mcp_servers/`](src/mcp_servers), [`gateway.py`](src/tools/gateway.py), [`test_mcp_stdio.py`](tests/unit/test_mcp_stdio.py) |
| Hotel search through Tavily | **Tested against mocked HTTP.** Needs a `TAVILY_API_KEY`. Without one the hotels server is not started and the plan says search is not configured | [`src/tools/`](src/tools/__init__.py), [`test_tools.py`](tests/unit/test_tools.py) |
| Weather through Open-Meteo | **Tested against mocked HTTP.** No key needed. Not exercised live in my verification | same |
| Flight search | **Mock data**, labelled `"source": "mock"`. The MCP server is real, the fares are not | [`flights.py`](src/mcp_servers/flights.py) |
| Itinerary | **First draft is a template**: one entry per day with real dates, and hotel neighbourhoods from a fixed list. **Revisions after feedback are written by the model**, limited to the activity text | [`graph.py`](src/agents/graph.py) |
| Budget | Flight cost is checked against your budget. The split across other categories is a **rule of thumb** | [`graph.py`](src/agents/graph.py) |
| SSE streaming API | **Working**, including the approval resume | [`planning.py`](src/api/routes/planning.py), [`streaming.py`](src/api/streaming.py) |
| PostgreSQL thread and message memory | **Working**, tested on real PostgreSQL | [`threads.py`](src/memory/threads.py) |
| Three-judge eval layer | **Implemented and unit-tested.** Not in the request path | [`gate.py`](src/evals/gate.py) |
| DeepEval agent evals and the merge gate | **Built and wired into CI** (`agent-evals`). The plumbing is verified with a stub judge and 71 tests. **No live score exists** (the one manual run failed before scoring, for two bugs that are now fixed), and the job skips (green) when the API keys are not set. It blocks a merge only after the keys are added as repository secrets and the job is a required status check | [`evals/`](evals), [`eval_gate.py`](.github/scripts/eval_gate.py), [`ci.yml`](.github/workflows/ci.yml) |
| Model fallback chain | **Implemented and tested with fake clients.** Never tried against real providers. `deepseek-flash` comes from DeepSeek's documentation and has not been called live | [`llm.py`](src/core/llm.py) |
| Frontend | **Working.** Verified in a browser against a faked LLM, supervisor and network tools, with the real graph, stream and checkpointer behind it. There are no automated frontend tests | [`frontend/`](frontend) |
| End-to-end run with a real LLM key | **Not done yet**, in the API or in the browser | none |
| Docker image | **Not built on my machine.** The CI Verify workflow builds it | [`Dockerfile`](Dockerfile), [`verify.yml`](.github/workflows/verify.yml) |
| Public deployment | **None yet.** A Render Blueprint ([`render.yaml`](render.yaml)) is prepared. Server-Sent Events on Render's free tier are untested | [`DEPLOYMENT.md`](DEPLOYMENT.md) |
| Measured latency and cost per trip | **Not measured.** The `< 10 s` and `< $0.50` figures in the specs are targets. The 290 MB memory figure is an estimate from about 60 MB per measured server | [`specs/00-overview.spec.md`](specs/00-overview.spec.md) |

### Smaller known limits

- `trace_id` is empty in most log lines, because request-level tracing is not wired in yet.
- `settings.database.pool_size` is read but unused. The pool size is fixed at 2 to 20 connections.
- There is no login. A `user_id` is only a label sent by the client.
- The guard that stops two runs on one thread is per process, which fits a single API instance. Running several instances needs a shared lock.
- If the browser disconnects in the middle of a run, the run is cancelled and no plan is stored for it. The checkpoint keeps the last finished step.
- `delete_thread` removes only the thread row. Nothing calls it yet, and the checkpoints of a deleted thread would stay.
- The test files are not type-clean under strict pyright. CI checks `src`, and `src` has 0 errors.

---

## Roadmap with exit criteria

Each milestone ends with something I can demonstrate, not just something I can say.

```mermaid
flowchart LR
    M1["M1<br/>Real approval<br/>done"] --> M2["M2<br/>Evals in the loop<br/>built, not yet run live"]
    M2 --> M3["M3<br/>Real tools<br/>MCP done, live flights open"]
    M3 --> M4["M4<br/>LLM first draft"]
    M4 --> M5["M5<br/>Deploy and measure"]

    classDef done fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef part fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef next fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    class M1 done;
    class M2,M3 part;
    class M4,M5 next;
```

| Milestone | What changes | Exit criterion, something I can demonstrate |
|---|---|---|
| M1 Real approval | **Done.** `interrupt()` plus the Postgres checkpointer, so the graph pauses and resumes | Tests that pause, approve and resume, reject and re-plan, hit the cap, and survive a restart while paused |
| M2 Evals in the loop | **Partly done.** The golden set, the DeepEval metrics, the gate and the CI job exist. Still open: a run with real keys, setting the bars from it, and making the job a required check | A deliberately bad change is blocked by CI |
| M3 Real tools | **Partly done.** The tools are MCP servers. Still open: live flight data | A plan with no mock data in it |
| M4 LLM first draft | Replace the template first draft with a model-written plan and real neighbourhood data | Judge pass rates reported with the sample size |
| M5 Deploy and measure | Render or Vercel plus a container host, then load measurement | p50 and p95 latency and cost per trip, measured and published |

---

## Run it

Prerequisites: Python 3.11, Node.js 18 or newer, and either Docker or a local PostgreSQL.

**With Docker** (starts PostgreSQL and the API):

```bash
git clone https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph.git
cd Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph
cp .env.example .env        # set DEEPSEEK_API_KEY at least; OPENAI_API_KEY is the fallback, TAVILY_API_KEY is for hotels
docker compose up -d --build
curl http://localhost:8000/ready
```

**Frontend** (the browser calls the API directly, so set its address if it is not `localhost:8000`):

```bash
cd frontend
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                  # http://localhost:3000
```

**Without Docker:** start your own PostgreSQL, set `DATABASE_URL` and `DEEPSEEK_API_KEY` (add `OPENAI_API_KEY` for the fallback), then run `python main.py`. The MCP servers start by themselves as subprocesses. `MCP_ENABLED=false` runs the tools in-process instead.

**Tests:**

```bash
pip install -r requirements-eval.txt     # the app plus deepeval, which the eval-suite tests need
DATABASE_URL=postgresql://user:pass@localhost:5432/yatra_test pytest tests -q
```

Unit tests use dummy keys and never call a model. Without DeepEval installed, `tests/unit/test_eval_suite.py` skips itself. One of them starts a real MCP server subprocess, so it needs no network but does need Python to start a child process. The integration tests need a reachable PostgreSQL and fake the LLM.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/plan` | Start or continue a planning thread. Streams `thread`, `progress`, `plan`, `approval_required`, `done` or `error` frames as SSE |
| `GET` | `/api/threads/{thread_id}` | Thread, history, message count, latest plan and the approval request it is waiting on. 404 if unknown |
| `PUT` | `/api/threads/{thread_id}/approve` | Answer a paused plan with `{"approved": true}` or `{"approved": false, "feedback": "..."}`. Streams the resumed run in the same SSE format |
| `GET` | `/health` | Liveness: the process is up, and the list of features |
| `GET` | `/ready` | Readiness: the database answers, plus the state of each MCP server. 503 if the database does not answer |

The approve endpoint answers with a status code that says what is wrong:

| Code | Meaning |
|---|---|
| 404 | The thread does not exist, or the id is not a valid UUID |
| 400 | A rejection without feedback |
| 409 | No plan is waiting for an answer, or a run on this thread is still in progress |
| 422 | The body is not a valid decision |
| 500 | A generic "Could not record the approval." The real error is logged, not returned |

A plan has one of four statuses: `awaiting_approval`, `approved`, `revision_limit` (the cap was reached and the last draft is not approved) or `rejected` (the guardrail refused the request).

## Repository map

```text
src/
  agents/       graph.py, runtime.py, routing.py, supervisor.py, trip.py, plan.py, state.py
  api/          FastAPI app factory, SSE runner (streaming.py), routes (plan, approval, health)
  core/         config, LLM factory, telemetry, errors, startup
  evals/        gate.py and the safety, factuality and budget judges (request-time, not in the request path)
  memory/       PostgreSQL pool, threads, migrations, saver.py (the LangGraph checkpointer)
  mcp_servers/  hotels (Tavily), flights (mock), weather (Open-Meteo): one stdio MCP server each
  tools/        the tool functions, and gateway.py that calls them through MCP with a fallback
evals/          DeepEval agent evals: eval_agent.py, 15 goldens, a custom plan judge, report writer
frontend/       Next.js 15 app: home, plan, results and approve pages
specs/          10 specification files that drive the build
tests/          unit (357) and integration (37) suites
docs/           AUDIT.md, BLOCKED.md and the build trail
.mcp.json       the same three servers, for any MCP client such as Claude Code
requirements-eval.txt  requirements.txt plus deepeval, for the test and eval jobs
DEPLOYMENT.md   environment variables, Render, Vercel, container host, checklist
render.yaml     Render Blueprint: PostgreSQL, API (Docker) and frontend (Node)
verify.sh       the definition of done, in 3 tiers
```

---

## How this was built

The project was built spec first, with an AI coding agent in the loop and a human-written bar for what counts as done. The specs, the audit and the blocker report are the evidence of that process. The first audit found 11 issues, including a provider mix-up (DeepSeek wired through a Groq client), stub tools and stub agents. A later review found the defects in the table above. All of them are documented, and the fixes are in the history.

**Author:** Amith Ganta, [github.com/Amith-Ganta](https://github.com/Amith-Ganta)
