# Yatra AI

### A multi-agent travel planner that treats the LLM as an untrusted component: guarded at the door, paused for a human before anything is final, and held to tests that run against a real database.

[![CI Pipeline](https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/actions/workflows/ci.yml)
[![Verify](https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/actions/workflows/verify.yml)
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://yatra-ai---a-multi-agent-travel-planner-with-langgraph.streamlit.app/)

Built with **LangGraph, FastAPI, PostgreSQL, MCP, Next.js, Streamlit and Server-Sent Events**. Specified first, built spec by spec, then reviewed against its own claims. The defects that review found are listed below with the tests that now guard them.

---

## Try it live

**https://yatra-ai---a-multi-agent-travel-planner-with-langgraph.streamlit.app/**

Status check on 4 October 2026. The page was loaded and read. **No plan was submitted**, so this is a check that the app is up and configured, not a test of a full trip.

- The page renders, with a trip form and a "Describe your trip" tab.
- The sidebar lists the models in order: `deepseek:deepseek-flash`, then `openai:gpt-4.1-mini`, and says `Keys: DeepSeek set, OpenAI set`.
- Tool status: flights **ready**, weather **ready**, hotels **skipped** because no `TAVILY_API_KEY` is set. So the flights and weather MCP servers started on Streamlit Community Cloud, and hotel search is off until I add a Tavily key.

Please read before you click:

- There are example buttons under "Try an example:". The third one is off-topic on purpose ("Write me a Python script that sorts a list.") so you can see the guardrail refuse it.
- Every plan makes real LLM calls on my API keys. Please try one or two requests, not a stress test.
- Streamlit Community Cloud puts an app to sleep after about 12 hours without visitors. The first load after that takes longer, and I have not measured how long.
- Plans live in the memory of one process. A restart or a sleep loses them, and the sidebar says so.
- Flights are mock data, labelled `"source": "mock"` in every plan.

---

## How to read this README

| You have | Read | What you get |
|---|---|---|
| 30 seconds | [In plain English](#in-plain-english) and [What the evidence supports](#what-the-evidence-supports) | What the project is, and how far each claim is proven |
| 3 minutes | [What this project shows](#what-this-project-shows), [Questions a hiring manager might ask](#questions-a-hiring-manager-might-ask) and [Not in this repo](#not-in-this-repo) | The skills, the honest gaps, and what I did not build |
| 15 minutes | [System architecture](#system-architecture) to [Deployment and operations](#deployment-and-operations) | The design in diagrams, with the code and tests behind each one |

If you only open four files, open [`graph.py`](src/agents/graph.py), [`supervisor.py`](src/agents/supervisor.py), [`gateway.py`](src/tools/gateway.py) and [`docs/BLOCKED.md`](docs/BLOCKED.md).

---

## In plain English

You describe a trip. Yatra first decides whether it is a real travel request. If it is, small specialist programs look up flights, hotels and weather, a budget check runs, and a day-by-day draft is written. **Then the system stops and waits for a person.** You approve the draft, or you send it back with feedback. This can happen up to 3 times. Nothing is final until a person says yes, and a draft that was never approved is labelled that way.

```mermaid
flowchart TB
    A(["You describe<br/>a trip"]) --> B{"Is it a real<br/>travel request?"}
    B -->|"no, or the check fails"| X["Politely refused<br/>nothing is looked up"]
    B -->|yes| C["Specialists look up<br/>flights, hotels, weather"]
    C --> D["Budget check<br/>and a day-by-day draft"]
    D --> E{"A person decides"}
    E -->|"approve"| F["Final plan<br/>marked approved"]
    E -->|"send back with feedback<br/>up to 3 times"| D
    E -->|"still not approved<br/>after 3 revisions"| G["Latest draft kept<br/>marked not approved"]

    classDef guard fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef gate fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    class B,X guard;
    class E gate;
    class F,G good;
```

The interesting part is not the travel. Most "AI agent" demos prove that a model can talk. This project is about the engineering around the model that decides whether you can trust it: what happens when the model is wrong, slow, or down, and how I know.

---

## The 60-second version

- **A guardrail that fails closed.** Every request goes through a supervisor that returns a structured verdict. If the model errors, returns garbage, or answers `"allowed": "yes"` instead of a real boolean, the request is rejected, not waved through.
- **A real human in the loop.** After the itinerary is drafted, the graph stops at a LangGraph `interrupt()`. In the API version the paused run is saved in PostgreSQL by the `AsyncPostgresSaver` checkpointer, so nothing is running and nothing is lost if the server restarts. You answer later, and `Command(resume=...)` continues the same thread. Reject with feedback and the itinerary is revised, up to 3 revised drafts, then the last draft is kept and labelled as not approved.
- **Tools behind real MCP servers.** Flights, hotels and weather are three stdio MCP servers, started as subprocesses and called through `langchain-mcp-adapters`. If a server cannot start or a call fails, the same tool runs in-process, and every result says which path answered (`"via": "mcp"` or `"in-process"`).
- **Parallel specialists, deterministic routing.** Flight, hotel and weather research run as one parallel wave. Budget runs after the wave, because it needs the flight price. Which specialists run is the model's choice. The order in which the graph moves is plain Python, with a test that proves every node runs exactly once.
- **Evaluation in two layers.** Three LLM judges (safety, factuality, budget) are implemented and unit-tested, return JSON scores, and score `0.0` on an error instead of passing silently. They are not wired into the request path yet. A second layer, built with DeepEval after the [campusx agent-evals](https://github.com/campusx-official/agent-evals-deepeval) approach, runs 15 golden tasks through the real graph (approval loop included) and feeds a merge gate. [Two live runs are reported below, the first with what failed](#agent-evals-with-deepeval).
- **A model fallback chain.** The agents run on `deepseek-flash`. If a call raises (timeout, rate limit, outage), the same call is retried on OpenAI `gpt-4.1-mini`. A fallback with no API key is skipped with a warning, never an error. The unit tests use fake clients. The live eval runs went through the chain, but the logs do not show which model answered, so I have never seen it switch.
- **Two runtime shells over one core.** The same graph runs behind a FastAPI and Next.js stack (built and tested in CI, not deployed) and inside a Streamlit app (live).
- **Streaming end to end.** `graph.astream` is exposed over Server-Sent Events in the API, and the Streamlit page polls a background loop, so the traveller sees each agent finish while the others are still working.
- **Tests that touch a real database and a real subprocess.** 495 tests pass in CI. The 37 integration tests run against a real PostgreSQL 15, including one that pauses a plan, restarts the application and resumes it. Four more tests start a real MCP server over stdio instead of faking it.
- **A written audit trail.** Specs, an audit report, a blocker report, and a review that found the app could not serve a single database request even though CI was green. That story is told [below](#the-review-that-found-the-database-was-never-opened).

---

## What the evidence supports

Different claims in this README rest on different kinds of evidence. This ladder shows how far each kind reaches, from the cheapest at the bottom to the strongest at the top, and what is still missing.

```mermaid
flowchart BT
    R1["1. Specs<br/>10 files say what done means"] --> R2["2. Unit tests<br/>458, LLM faked, 4 real MCP subprocess tests"]
    R2 --> R3["3. Integration tests<br/>37, real PostgreSQL 15, LLM faked"]
    R3 --> R4["4. CI green on main<br/>CI Pipeline and Verify at 5dff231"]
    R4 --> R5["5. Live evals, real judge<br/>2 runs on 3 Oct, the first failed the gate"]
    R5 --> R6["6. Public URL checked<br/>4 Oct, page load only, tools ready"]
    R6 -.-> N1["Not yet recorded<br/>a full plan on the live URL"]
    R6 -.-> N2["Not yet observed<br/>a fallback switch with real providers"]
    R6 -.-> N3["Not measured<br/>latency, cost per trip, load"]

    classDef ok fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef planned fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    class R1,R2,R3,R4,R5,R6 ok;
    class N1,N2,N3 planned;
```

| Rung | What it proves | What it does not prove |
|---|---|---|
| Specs | The intent was written down before the code | That the code matches it. The audit found 11 gaps in the first pass |
| Unit tests | Each rule behaves as written, with a faked model | How a real model behaves |
| Integration tests | The graph, API and checkpointer work against a real database, including a restart while paused | Real provider calls, a real browser |
| CI green | A clean checkout builds, lints, type-checks and passes all tests, and the Docker image builds and answers `/health` and `/ready` | That the app is deployed anywhere |
| Live evals | The real graph, with real model calls and a real judge, passes a revised gate | That it would have passed a gate fixed in advance. The spread between runs is unknown |
| Public URL checked | The app is up, reachable and configured, on the day I checked | A full plan, hotel search, memory headroom, wake-up time, or that it stays up |

---

## Evidence at a glance

The CI figures come from the GitHub Actions runs for commits `e593cbf` and `5dff231` (4 October 2026). The other rows were checked on my Windows machine on the dates in the table.

| Signal | Value | Proof |
|---|---|---|
| Live deployment | Streamlit Community Cloud, checked on 4 October 2026 (page load only): models listed, both keys set, flights and weather MCP servers ready, hotels skipped. **No plan submitted** | [the live app](https://yatra-ai---a-multi-agent-travel-planner-with-langgraph.streamlit.app/), [`WORKING_URL.md`](WORKING_URL.md) |
| Orchestration | 9-node LangGraph `StateGraph` over a typed `TravelState`. On the approve-first-time path every node runs exactly once | [`graph.py`](src/agents/graph.py), [`test_graph_execution.py`](tests/unit/test_graph_execution.py) |
| Safety at the door | LLM guardrail with a JSON verdict. Fails closed on an error, an unparseable reply, or a non-boolean `allowed` | [`supervisor.py`](src/agents/supervisor.py), [`test_supervisor.py`](tests/unit/test_supervisor.py) |
| Human in the loop | `interrupt()` and `Command(resume=...)`. A rejection needs feedback. Revision cap of 3. With the PostgreSQL saver, a paused plan survives an application restart | [`graph.py`](src/agents/graph.py), [`approval.py`](src/api/routes/approval.py), [`test_api.py`](tests/integration/test_api.py) |
| Tools | 3 MCP servers over stdio through `langchain-mcp-adapters`, with an in-process fallback | [`src/mcp_servers/`](src/mcp_servers), [`gateway.py`](src/tools/gateway.py), [`test_mcp_stdio.py`](tests/unit/test_mcp_stdio.py) |
| Quality at the exit | 3 judges: safety, factuality, budget. Fail-safe score `0.0`. Not in the request path | [`src/evals/`](src/evals), [`test_evals.py`](tests/unit/test_evals.py) |
| Agent evals | DeepEval 4.1.5: Task Completion, Plan Quality, Plan Adherence and a custom plan judge, plus code checks for guardrail, routing and the approval loop, over 15 golden tasks. A gate script and a CI job (`agent-evals`) are wired to it. 74 key-free tests cover the plumbing. **Two live runs recorded below; the gate was revised between them** | [`evals/`](evals), [`eval_gate.py`](.github/scripts/eval_gate.py), [`test_eval_suite.py`](tests/unit/test_eval_suite.py) |
| Model fallbacks | `deepseek-flash`, then `gpt-4.1-mini` on a failure. Judges use `gpt-4o-mini` and never fall back. Tested with fake clients, not seen switching with real providers | [`llm.py`](src/core/llm.py), [`test_llm_factory.py`](tests/unit/test_llm_factory.py) |
| API | Async FastAPI, typed SSE frames, thread memory, `/ready` returns 503 until the database answers | [`src/api/routes/`](src/api/routes) |
| Persistence | PostgreSQL threads and messages, LangGraph checkpoints, pooled connections, idempotent migrations on startup, retry until the database is up | [`src/memory/`](src/memory), [`src/core/startup.py`](src/core/startup.py) |
| Frontends | Next.js 15 (App Router), React 18, Tailwind: 4 pages, 11 components, 2 SSE and thread hooks, `tsc` and `next build` clean. And the Streamlit app, which runs the same graph in its own process with no PostgreSQL and no API: 95 tests cover its formatting, start-up, background runtime and page flow | [`frontend/`](frontend), [`src/ui/`](src/ui), [`streamlit_app.py`](streamlit_app.py), [`test_ui_app.py`](tests/unit/test_ui_app.py) |
| Tests | **495 passed** in the `CI Pipeline` run on GitHub for commit `e593cbf`: 458 unit (95 of them for the Streamlit app) and 37 integration. The integration tests use a PostgreSQL 15 service container and a faked LLM. The run uses `requirements-eval.txt`, so the DeepEval tests are included. The next commit, `5dff231`, changed documentation only and its runs are green too | [`tests/`](tests) |
| Coverage | **91.30%** of `src`, measured locally with `pytest --cov=src` before the Streamlit code was added (not re-measured since). The MCP server files show 0% because they run in a subprocess that the coverage tool does not follow | `pytest.ini` |
| Static checks | `ruff` and `black` clean on `src`, `tests`, `evals` and `.github/scripts`. `pyright` 0 errors on `src` | [`ci.yml`](.github/workflows/ci.yml) |
| Container checks in CI | The `Verify` workflow builds the Docker image, starts it with `docker compose`, polls `/ready` and checks `/health`. The `build` job in CI Pipeline builds it again with no push | [`verify.yml`](.github/workflows/verify.yml), [`ci.yml`](.github/workflows/ci.yml) |
| Browser check | Next.js app: plan, live progress stream, redirect to the approval page, an empty rejection blocked, a rejection with feedback, the "revised draft N of 3" counter, the cap at 3 ending in "revision limit", approval, and the results page with its banners and weather. Driven in a real browser against the compiled Next.js build. The LLM, the supervisor and the three network tools were faked. The graph, the SSE stream, the plan documents and the PostgreSQL checkpointer were real | see [limits](#what-is-real-and-what-is-roadmap) |
| Method | 10 spec files drive the code. A written self-audit found 11 issues in the first pass | [`specs/`](specs), [`docs/AUDIT.md`](docs/AUDIT.md) |
| History | 86 commits from 27 to 30 September 2026, then 8 more from 3 to 4 October, before this README rewrite | `git log` |

---

## What this project shows

Each row is a skill, what I built to practise it, where to look, and how far it is proven. I would rather you read the "honest status" column from me than find it yourself.

| Skill | What I built | Where to look | Honest status |
|---|---|---|---|
| LLM orchestration | A 9-node LangGraph over typed state, with a parallel research wave and deterministic routing | [`graph.py`](src/agents/graph.py), [`routing.py`](src/agents/routing.py) | Working and tested. Every node runs once on the happy path |
| Guardrails | A fail-closed supervisor: input wrapped as data, strict boolean verdict, known-agent filter | [`supervisor.py`](src/agents/supervisor.py) | Tested with a fake model. Refusals also scored live in the evals (5 of 15 goldens) |
| Durable human approval | `interrupt()` and resume, a cap of 3 revisions, a rejection needs feedback | [`approval.py`](src/api/routes/approval.py) | Tested, including a restart while paused. The live Streamlit app uses an in-memory saver |
| Tool integration | Three stdio MCP servers with start-up and call timeouts and an in-process fallback | [`gateway.py`](src/tools/gateway.py), [`src/mcp_servers/`](src/mcp_servers) | Working. Flights are mock data. Hotels need a Tavily key |
| LLM evaluation | A DeepEval suite, a custom judge, and a gate script with three exit codes | [`evals/`](evals), [`eval_gate.py`](.github/scripts/eval_gate.py) | Two live runs. I revised the gate after the first one. It is not a required check yet |
| Model reliability | A fallback chain with a timeout and one retry | [`llm.py`](src/core/llm.py) | Tested with fake clients only. I have not seen a real switch |
| API design | Async FastAPI, typed SSE frames, meaningful status codes (400, 404, 409, 422) | [`src/api/`](src/api) | Tested against a real database. Not deployed |
| Data layer | PostgreSQL threads and messages, LangGraph checkpoints, idempotent migrations | [`src/memory/`](src/memory) | Tested on PostgreSQL 15 in CI |
| CI | Two GitHub Actions workflows: a strict gate and a definition of done | [`.github/workflows/`](.github/workflows) | Green on `main`. There is **no deploy job** |
| Containers | A non-root image with a `HEALTHCHECK`, and a compose file with health checks | [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) | Built in CI. Never built on my machine. Image not scanned |
| Testing | 495 tests, with a real database and a real subprocess where it matters | [`tests/`](tests) | Real provider calls, browser end-to-end tests and load tests are not automated |
| Operability | `/health` against `/ready`, structured logs, tool status in the sidebar | [`src/api/routes/`](src/api/routes), [`src/ui/`](src/ui) | `trace_id` is mostly empty. No metrics, alerts or dashboards |
| Security basics | Trust boundaries, a CORS allowlist, keys passed only to the process that needs them | [Security](#security) | No login, no rate limit, no dependency or secret scanning |
| Cloud deployment | The Streamlit app is live on Streamlit Community Cloud | [`DEPLOYMENT.md`](DEPLOYMENT.md) | Checked once, on 4 October 2026. The Render attempt for the API did not come up |
| Frontend | Next.js 15 with SSE hooks, and a Streamlit page | [`frontend/`](frontend), [`src/ui/`](src/ui) | Next.js was browser-checked with a faked LLM and has no automated tests. Streamlit has 95 tests |
| Working method | Specs first, an audit, a blocker report, and a ledger of what is and is not verified | [`specs/`](specs), [`docs/`](docs) | The process is documented in this repository |

```mermaid
mindmap
  root((Yatra AI))
    AI engineering
      LangGraph state machine
      Fail closed guardrail
      Human approval with interrupt
      MCP tool servers
      Model fallback chain
    Evaluation
      DeepEval golden tasks
      Custom GEval judge
      Merge gate with exit codes
      Hindsight stated openly
    Backend
      Async FastAPI
      Server Sent Events
      PostgreSQL and checkpoints
      Idempotent migrations
    DevOps
      Two GitHub Actions workflows
      Docker and compose health checks
      Streamlit Community Cloud
      Readiness against liveness
    Quality
      495 tests in CI
      Real database and subprocess
      Written audit and blocker report
    Not in this repo yet
      Kubernetes
      Load tests
      Monitoring stack
      Login and rate limits
```

---

## Questions a hiring manager might ask

**Is it deployed?** The Streamlit version, yes: the link is at the top. The FastAPI and Next.js version is built, tested in CI and run locally, but it is not deployed. I tried Render for the API. It did not come up and I did not find out why, so I do not claim it.

**Has it handled real traffic?** No. It was checked once on 4 October 2026, with a page load. There is no load test and no usage data.

**Was a full plan run on the live app?** No full plan on the live URL is recorded in this repository yet. The live evals did run the real graph with real model calls, and a stubbed-model run was driven in a browser. A real plan in a browser against real keys is the next check I want to record.

**Does the model fallback work?** It is tested with fake clients that raise. With real providers I have never seen it switch, because the logs do not record which model answered.

**Are the tests just mocks?** Partly, on purpose. The LLM is faked in the unit and integration tests, and the HTTP calls to Tavily and Open-Meteo are mocked. The database is real (PostgreSQL 15), and four tests start a real MCP server over stdio. The live evals use real models. Details are in [Test layers](#test-layers).

**Why two runtime shells?** The API shell shows the design I would use with several users: a durable checkpoint in PostgreSQL and a streaming API. It needs a container host, a database and a frontend host. The Streamlit shell runs the same graph in one process with an in-memory saver, so it could go online in one step. Both share the same core, so the Streamlit app is not a different program.

**What happened with Render?** The Blueprint was applied, the web service came up, and the API service ended as "Failed deploy". I had no access to the logs and I did not find the cause. I suspect the database URL, but I did not confirm it. I moved on to Streamlit.

**What does a trip cost?** I do not know. `TravelState` has fields for tokens and cost, but nothing fills them, and I have not measured it.

**What would you do next?** In this order: record one real plan on the live URL, add a spend cap and a rate limit, make `agent-evals` a required check and run it more often to see the spread, fill `trace_id`, and then M4 and M5 in the [roadmap](#roadmap-with-exit-criteria).

---

## System architecture

### System context

Who talks to what. Flights have no external provider: they are mock data.

```mermaid
flowchart LR
    T(["Traveller"]) -->|"describes a trip<br/>approves or rejects"| Y["Yatra AI<br/>multi-agent planner"]
    Y -->|"agent and revision calls<br/>primary model"| DS["DeepSeek API"]
    Y -->|"fallback calls<br/>gpt-4.1-mini"| OA["OpenAI API<br/>also the judge in evals"]
    Y -->|"hotel search<br/>needs a key"| TV["Tavily"]
    Y -->|"forecast<br/>no key needed"| OM["Open-Meteo"]
    Y -.->|"mock data<br/>no provider"| FX["Flight fixtures"]
    GH["GitHub Actions"] -->|"lint, tests, evals,<br/>docker build"| Y
    SC["Streamlit Community Cloud"] -->|"hosts the live app"| Y

    classDef live fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef mock fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    class Y,DS,OA,TV,OM,GH,SC live;
    class FX mock;
```

### Containers: one core, two shells

```mermaid
flowchart TB
    subgraph SHELL1["Shell 1: Streamlit app, LIVE"]
        direction LR
        ST["streamlit_app.py<br/>src/ui/"] --> RT["Background asyncio loop<br/>InMemorySaver, no database"]
    end

    subgraph CORE["Shared core: src/agents, src/tools, src/core"]
        direction LR
        GR["LangGraph<br/>9 nodes"] --- TL["Tool gateway<br/>MCP with fallback"]
        TL --- LF["LLM factory<br/>fallback chain"]
    end

    subgraph SHELL2["Shell 2: API stack, built and tested in CI, not deployed"]
        direction LR
        FE["Next.js 15<br/>frontend"] --> API["FastAPI<br/>SSE"]
        API --> PGS[("PostgreSQL<br/>AsyncPostgresSaver")]
    end

    RT --> GR
    API --> GR

    classDef live fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef planned fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    class ST,RT,GR,TL,LF live;
    class FE,API,PGS planned;
```

Green is live. Purple dashed is built and tested in CI but not deployed.

### Component view of the API shell

```mermaid
flowchart TB
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

    MCP -.->|"server down<br/>or MCP_ENABLED=false"| FB["In-process tools<br/>the same functions"]
    G -.-> EV["Eval layers<br/>not in request path"]

    classDef live fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef mock fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef planned fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    class FE,API,PG,G,LLM,M1,M3,FB live;
    class M2 mock;
    class EV planned;
```

Here green means working code, amber is mock data, and purple dashed is built and tested but not wired into the request path.

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
3. **Rejection is a first-class path.** A refused request goes straight to `final_response`. It never touches a tool and it never pauses for approval.
4. **The approval node has no side effects before `interrupt()`.** On resume LangGraph runs the node again from its first line, so anything done before the pause would be done twice. The node only builds the question, pauses, and reads the answer.
5. **A revision changes the words, not the facts.** When you reject a draft, the model may rewrite only the activity text of each day. Day numbers, dates and the weather forecast stay as computed. If the model's reply is unusable, the previous draft is kept and the plan says that your feedback was not applied. Your feedback is passed to the model inside tags as data, not as instructions.

### Who reads and writes what

`TravelState` is a typed dictionary. Each node owns a small set of keys, and `new_request_state()` resets every per-request key at the start of a request, so one request cannot leak into the next. Solid arrows are writes, dotted arrows are reads.

```mermaid
flowchart TB
    MSG[("message<br/>thread_id")] --> SUP["supervisor"]
    SUP --> VERD[("allowed, reason<br/>selected_agents<br/>trip_constraints")]

    VERD -.-> FL["flight"]
    VERD -.-> HO["hotel"]
    VERD -.-> WE["weather"]
    FL --> FO[("flight_output")]
    HO --> HOO[("hotel_output")]
    WE --> WO[("weather_output")]

    VERD -.-> BU["budget"]
    FO -.->|"best_option price"| BU
    BU --> BO[("budget_output")]

    VERD -.-> IT["itinerary"]
    WO -.->|"forecast"| IT
    HOO -.->|"hotels"| IT
    FB[("feedback<br/>revision_count")] -.-> IT
    IO[("itinerary_output")] -.->|"previous draft<br/>reused only if length equals days"| IT
    IT --> IO

    IO -.-> HA["human_approval"]
    HA --> DEC[("human_approval<br/>feedback")]
    DEC -.-> RV["revise"]
    RV --> FB

    VERD -.->|"allowed"| FR["final_response"]
    DEC -.-> FR
    IO -.-> FR
    FB -.->|"revision_count"| FR
    FR --> OUT[("final_response<br/>plan, summary, approved, revisions")]

    classDef node fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    classDef state fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    class SUP,FL,HO,WE,BU,IT,HA,RV,FR node;
    class MSG,VERD,FO,HOO,WO,BO,FB,IO,DEC,OUT state;
```

Three fields in `TravelState` are declared but never filled: `model_used`, `total_tokens` and `cost_usd`. That is why I give no token or cost figure in this README.

### The guardrail, step by step

The guardrail is the first node and the only one that decides whether the rest runs. Every path that is not a clean "yes" ends in a refusal.

```mermaid
flowchart TD
    M["User message"] --> W["Wrap in user_request tags<br/>the model is told it is data"]
    W --> L["LLM call<br/>reply must be JSON only"]
    L -->|"the call raises"| X
    L --> P["parse_llm_json<br/>accepts plain JSON or a fenced block"]
    P -->|"not a JSON object"| X
    P --> A{"allowed is True?<br/>a real boolean"}
    A -->|"false, the string yes,<br/>the string true, missing"| R["Refuse<br/>the verdict carries a reason"]
    A -->|"exactly true"| K["Keep only known agents<br/>flight, hotel, weather, budget"]
    K --> C{"trip_constraints<br/>is a dict?"}
    C -->|"yes"| GO["Allowed: route to the research wave"]
    C -->|"no"| E["Use an empty dict"] --> GO
    X["Any exception<br/>logged on the server only<br/>generic refusal returned"]

    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    class X,R bad;
    class GO good;
```

The refusal message for an error is fixed ("We could not process your request right now. Please try again."), so a provider's error text never reaches the traveller. Tests: [`test_supervisor.py`](tests/unit/test_supervisor.py).

---

## Human approval as a state machine

The same loop, seen as states. The three end states map to the plan statuses `rejected`, `approved` and `revision_limit` that the API and the page report.

```mermaid
stateDiagram-v2
    [*] --> Guarding
    Guarding --> Refused: allowed is not true or any error
    Guarding --> Researching: allowed and research agents selected
    Guarding --> Budgeting: no research but budget selected
    Guarding --> Drafting: nothing selected
    Researching --> Budgeting: budget selected
    Researching --> Drafting: budget not selected
    Budgeting --> Drafting
    Drafting --> AwaitingApproval: interrupt and the run is saved
    AwaitingApproval --> Approved: approved is exactly true
    AwaitingApproval --> Revising: rejected with feedback and revisions left
    AwaitingApproval --> RevisionLimit: rejected at the cap of 3
    Revising --> Drafting: revision count plus one
    Refused --> [*]
    Approved --> [*]
    RevisionLimit --> [*]
    note right of AwaitingApproval
        Nothing is running here.
        API shell: the run waits in the PostgreSQL checkpoint.
        Streamlit shell: it waits in process memory.
    end note
```

---

## Request lifecycle: plan, pause, approve

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 170, "messageAlign": "left"}}}%%
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

## Streamlit front end

The Streamlit app is the second shell over the same core. It does not need the FastAPI service or PostgreSQL, which is why it could go online first.

Streamlit re-runs the script on every click, in a worker thread that has no event loop. The graph, the MCP sessions and the LLM clients cannot live in that thread, so they live on one persistent background asyncio loop, created once with `st.cache_resource`. The page starts a turn, keeps a handle in the session, and polls it.

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 170, "messageAlign": "left"}}}%%
sequenceDiagram
    autonumber
    participant B as Browser
    participant S as Script thread
    participant L as yatra-planner loop
    participant G as LangGraph
    participant P as Providers

    B->>S: click, Streamlit re-runs the script
    S->>L: start_turn via run_coroutine_threadsafe
    L-->>S: TurnHandle, kept in session state
    L->>G: astream updates, inside wait_for 300 s
    G->>P: LLM and MCP calls
    P-->>G: results
    loop poll every 0.4 s
        S->>L: ask the handle for progress
        L-->>S: node names finished so far
        S-->>B: st.status lists the agents
    end
    alt graph reached interrupt
        L->>G: aget_state
        L-->>S: TurnResult with the plan and the approval request
        S-->>B: draft and the decision controls
    else any exception or the 300 s limit
        L-->>S: PlanningError with the fixed message
        S-->>B: We could not plan this trip right now
    end
```

- **Secrets.** On Streamlit Community Cloud, keys come from the app's Secrets box. [`src/ui/bootstrap.py`](src/ui/bootstrap.py) copies them into the environment before the settings module is imported, and a variable that is already set wins. No `DATABASE_URL` is needed, because a placeholder is set for the settings object.
- **The page is guarded the same way as the API.** The supervisor still refuses off-topic requests, a rejection needs feedback, and a failed run shows one fixed message, never the provider's error text.
- **The approve button cannot be hit by accident.** The decision controls are plain widgets and not a form, because in a Streamlit form Ctrl+Enter in the feedback box would submit the first button. A test pins this: [`test_ui_app.py`](tests/unit/test_ui_app.py).
- **Each browser session has its own thread.** A `streamlit-` plus 8 hex characters id keeps visitors apart.
- **The limits.** Plans live in the memory of one process, so a restart or a sleeping app loses them. There is no login, and every plan costs real LLM calls.

How to run it and deploy it: [Run it](#run-it) and [`DEPLOYMENT.md`](DEPLOYMENT.md), section 13.

---

## Tools and models

### MCP: start-up and call path

The tool gateway ([`gateway.py`](src/tools/gateway.py)) is written so that a broken tool server degrades one tool and never the whole plan. `start()` never raises. It records `ready`, `skipped: ...` or `failed: ...` for each server, and that is what the Streamlit sidebar shows.

```mermaid
flowchart TB
    subgraph START["Start up: toolbox.start never raises"]
        direction TB
        S0{"MCP_ENABLED<br/>is false?"} -->|"yes"| SK0["No servers<br/>tools run in-process"]
        S0 -->|"no"| S1["Servers start one at a time<br/>20 s limit each"]
        S1 --> K{"Needs a key<br/>and it is missing?"}
        K -->|"hotels without<br/>TAVILY_API_KEY"| SK["skipped<br/>the plan says search<br/>is not configured"]
        K -->|"no"| T{"stdio session<br/>up in 20 s?"}
        T -->|"yes"| RD["ready"]
        T -->|"timeout or error"| FL["failed<br/>reason recorded"]
    end

    subgraph CALL["Every tool call"]
        direction TB
        C0["An agent asks for a tool"] --> C1{"Server ready?"}
        C1 -->|"no"| IP["Run the same function<br/>in-process<br/>via: in-process"]
        C1 -->|"yes"| C2["MCP call<br/>25 s limit"]
        C2 -->|"answers"| MC["Result<br/>via: mcp"]
        C2 -->|"timeout or error"| IP
    end

    START ~~~ CALL

    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef warn fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    class RD,MC good;
    class SK,SK0,IP warn;
    class FL bad;
```

Each MCP server is started with only the environment variables it needs, so a tool process never sees the database URL or the LLM keys. On the live app today: flights ready, weather ready, hotels skipped.

### Model fallback chain

```mermaid
flowchart TB
    N["An agent node<br/>needs a model call"] --> P1["Primary<br/>deepseek-flash<br/>45 s timeout, 1 retry"]
    P1 -->|"answers"| OUT["Reply goes to the<br/>node's own validation"]
    P1 -->|"raises: timeout,<br/>rate limit, outage"| P2["Fallback<br/>openai gpt-4.1-mini"]
    P2 -->|"answers"| OUT
    P2 -->|"raises"| ERR["The exception reaches<br/>the node's error handler"]
    OUT --> V{"Usable?"}
    V -->|"empty or bad content"| H["Not a fallback case<br/>the node refuses or keeps<br/>the previous draft"]
    NK["A fallback with no key<br/>is skipped with a warning<br/>when the chain is built"] -.-> P2
    J["Judge in the evals<br/>gpt-4o-mini<br/>no fallbacks"]

    classDef ok fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef warn fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    class P1,P2,OUT ok;
    class H,NK,J warn;
    class ERR bad;
```

The chain uses LangChain's `with_fallbacks`, which catches raised errors only, so a bad answer does not trigger it. That is by design, and the node handles bad content itself. The worst case on a failover is about 90 seconds for one call (45 s plus one retry, then the fallback). I tested this with fake clients, and I have not seen a real switch.

---

## Data model

The API shell stores threads and messages itself, and LangGraph's checkpointer stores the run state in its own tables. The two sets of tables share only the `thread_id` value. There is no foreign key between them, so deleting a thread row does not delete its checkpoints (listed under [known limits](#smaller-known-limits)).

```mermaid
erDiagram
    THREADS ||--o{ MESSAGES : "has, deleted together by cascade"
    THREADS ||..o{ CHECKPOINTS : "shares thread_id value, no FK"
    THREADS ||..o{ CHECKPOINT_BLOBS : "shares thread_id value, no FK"
    THREADS ||..o{ CHECKPOINT_WRITES : "shares thread_id value, no FK"

    THREADS {
        uuid thread_id PK
        varchar user_id
        timestamp created_at
        timestamp updated_at
        jsonb metadata
    }
    MESSAGES {
        uuid message_id PK
        uuid thread_id FK
        varchar role
        text content
        jsonb metadata
        timestamp created_at
    }
    CHECKPOINTS {
        text thread_id
    }
    CHECKPOINT_BLOBS {
        text thread_id
    }
    CHECKPOINT_WRITES {
        text thread_id
    }
```

`threads` and `messages` come from [`001_init.sql`](src/memory). The checkpoint tables (plus `checkpoint_migrations`) are created by `AsyncPostgresSaver.setup()`, and I show only the column they share with `threads`. Indexes on the first two tables: `idx_user_id`, `idx_created_at` and `idx_thread_id_created_at`. **The live Streamlit app does not use this database at all.**

---

## Security

I did not run a formal threat model. This is what I thought about, what the code does, and what is left open.

### Trust boundaries

```mermaid
flowchart LR
    subgraph UNTRUSTED["Untrusted input"]
        U1["Trip message"]
        U2["Rejection feedback"]
        U3["Replies from the LLM"]
    end

    subgraph CONTROLS["Controls in code"]
        C1["Input wrapped in tags<br/>and presented as data"]
        C2["Booleans checked with is True<br/>JSON parsed strictly"]
        C3["Agent list filtered to known names<br/>constraints must be a dict"]
        C4["A revision may change<br/>activity text only"]
        C5["Generic error text to the user<br/>details only in logs"]
        C6["Each MCP subprocess gets<br/>only the keys it needs"]
    end

    subgraph TRUSTED["Trusted code"]
        T1["routing.py<br/>plain Python"]
        T2["Graph nodes<br/>and typed state"]
    end

    subgraph PROTECTED["Protected"]
        P1["LLM and Tavily keys"]
        P2[("DATABASE_URL")]
    end

    U1 --> C1 --> T2
    U2 --> C1
    U3 --> C2 --> C3 --> T1
    T2 --> C4
    T2 --> C5
    C6 --> P1
    C6 -.->|"never given"| P2

    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef gate fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    class U1,U2,U3 bad;
    class C1,C2,C3,C4,C5,C6 gate;
    class T1,T2,P1,P2 good;
```

### Threat model, short version

| Threat | Control | Proof | What is still open |
|---|---|---|---|
| Prompt injection in the trip message | The message goes to the supervisor inside `<user_request>` tags as data, the verdict must be strict JSON with `allowed is True`, and routing is plain Python | [`test_supervisor.py`](tests/unit/test_supervisor.py) | Tags reduce injection and do not remove it. The live evals have only 5 refusal goldens |
| Prompt injection in revision feedback | Feedback is passed in tags as data, and a revision may change only the activity text. Day numbers, dates and the forecast stay as computed | [`test_graph_execution.py`](tests/unit/test_graph_execution.py) | The activity text is model-written and shown to the user |
| Malformed or hostile model output | `parse_llm_json`, `is True`, the `KNOWN_AGENTS` filter, a dict check on `trip_constraints` | [`test_supervisor.py`](tests/unit/test_supervisor.py) | None known |
| Secret leakage | Keys come from the environment or the Streamlit Secrets box. Errors are logged on the server and the user gets a fixed message. MCP subprocesses get only what they need. `.streamlit/secrets.toml` is git-ignored | [`test_ui_runtime.py`](tests/unit/test_ui_runtime.py), [`gateway.py`](src/tools/gateway.py) | No automated secret scanning in CI |
| Cross-origin calls to the API | The CORS allowlist defaults to `localhost:3000` (finding C1) | [`test_cors.py`](tests/unit/test_cors.py) | Every deployment must set `CORS_ORIGINS` |
| A public URL with no login that spends my credits | **None in the code** | none | I have not checked the Streamlit sharing settings or the provider spend limits for this app |
| Known vulnerabilities in dependencies | I found the Next.js advisories by hand (finding N1) and upgraded | `next build` and the browser flow | No Dependabot and no scanner |
| Container privileges | The image runs as a non-root user, `appuser`, UID 1000 | [`Dockerfile`](Dockerfile) | The image is not scanned |
| Two runs resuming one checkpoint | A 409 guard on a running thread | [`test_api.py`](tests/integration/test_api.py) | The guard is per process, so it fits one API instance |
| The revision loop used to burn credits | A cap of 3 revisions, and a 300 s limit per Streamlit turn | [`test_api.py`](tests/integration/test_api.py), [`test_ui_runtime.py`](tests/unit/test_ui_runtime.py) | No rate limit per visitor |

---

## Delivery pipeline

### CI and CD

Two workflows run on every push to `main` and on pull requests. **There is no deploy job.** I deployed the Streamlit app by hand in the Streamlit dashboard, so the live app does not update by itself when CI passes.

```mermaid
flowchart LR
    DEV(["git push<br/>or pull request"]) --> CIP
    DEV --> VER

    subgraph CIP["CI Pipeline: ci.yml"]
        direction TB
        L["lint<br/>ruff, black --check, pyright on src"]
        T["test<br/>postgres:15-alpine service<br/>pytest with coverage, dummy keys"]
        AE["agent-evals<br/>pull request or manual run only<br/>45 min limit, then eval_gate.py"]
        BD["build<br/>docker buildx, no push"]
        L --> AE
        T --> AE
        L --> BD
        T --> BD
    end

    subgraph VER["Verify: verify.yml"]
        direction TB
        V1["Tier 1<br/>docker build, compose up<br/>poll /ready 30 times, GET /health, down"] --> V2["Tier 2<br/>pytest tests/unit"]
        V2 --> V3["Tier 3<br/>frontend npm run build, Node 20"]
    end

    AE --> ART["Artifact<br/>agent-eval-reports"]
    CIP --> NODEP["No deploy job"]
    VER --> NODEP
    NODEP -.-> MAN["I deploy by hand<br/>in the Streamlit dashboard"]

    classDef ok fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef planned fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    classDef doc fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    class L,T,BD,V1,V2,V3 ok;
    class AE,ART doc;
    class NODEP,MAN planned;
```

The two workflows have different jobs. **CI Pipeline** is the strict gate: lint, types and the full test suite against a PostgreSQL service. **Verify** is the definition of done: does the container boot, does the database answer on `/ready`, do the unit tests pass, does the frontend build. `agent-evals` runs on a pull request or a manual run, and it skips itself (green) if the API keys are missing. It blocks a merge only after it is made a required status check, which I have not done yet. The same three tiers are in [`verify.sh`](verify.sh) for a local run, and it hands Tier 1 to GitHub Actions when no Docker daemon is available.

The latest `Verify` run on `main` finished with every tier green in 3 minutes 46 seconds. Its only annotations were GitHub's Node.js 20 deprecation notice and the note that `ubuntu-latest` moves to Ubuntu 26 on 19 October 2026. I have not changed the workflows for either yet.

### Quality is checked in three places

```mermaid
flowchart LR
    subgraph RT["Runtime"]
        direction TB
        R1["Supervisor guardrail<br/>fails closed"] --> R3["Human approval<br/>nothing is final<br/>until a person says so"]
        R3 --> R2["Judges: safety, factuality, budget<br/>judge error gives score 0.0<br/>not wired in yet"]
    end

    subgraph CI["Every push"]
        direction TB
        C1["Lint, types, tests<br/>real PostgreSQL service"] --> C2["Docker boots and answers<br/>/ready and /health"]
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
    class R2 planned;
    class A1 doc;
```

### Test layers

```mermaid
pie showData
    title Tests that passed in CI, 495 in total
    "Unit tests, not the Streamlit app" : 363
    "Unit tests, Streamlit app" : 95
    "Integration tests, real PostgreSQL 15" : 37
```

| Layer | Count | What is real | What is faked |
|---|---|---|---|
| Unit, not the Streamlit app | 363 | Four tests start a real MCP server subprocess over stdio. The routing, guardrail and state rules run as written | The LLM (fake clients). HTTP calls to Tavily and Open-Meteo (mocked) |
| Unit, Streamlit app | 95 | The real graph, the real background runtime and page flow through Streamlit's `AppTest` | The model |
| Integration | 37 | A PostgreSQL 15 service container, the real API, the real checkpointer, a restart while a plan is paused | The LLM |
| Not in the test suite | none | | Real provider calls (apart from the live evals), automated browser end-to-end tests, load tests |

### Agent evals with DeepEval

`python -m evals.eval_agent` runs 15 golden tasks (10 the supervisor must allow, 5 it must refuse) through the real 9-node graph. A scripted traveller answers the approval question: approve at once, reject once with feedback, or reject until the revision cap. Each task becomes one DeepEval trace across the pause and the resume.

```mermaid
flowchart TB
    G["15 golden tasks<br/>10 allowed, 5 refused"] --> TR["Scripted traveller<br/>approve now, reject once,<br/>reject to the cap"]
    TR --> RG["The real 9-node graph<br/>flights from fixtures"]
    RG --> TC["One DeepEval trace per task<br/>across pause and resume"]

    TC --> CC["Code checks<br/>Guardrail, Approval Loop, Routing"]
    TC --> DE["DeepEval<br/>Task Completion gated<br/>Plan Quality and Plan Adherence<br/>report only"]
    TC --> CJ["Custom GEval judge<br/>gpt-4o-mini, no fallbacks"]

    CC --> GATE{"eval_gate.py"}
    DE --> GATE
    CJ --> GATE
    GATE -->|"exit 0"| PASS["Pass, or skip<br/>when keys are missing"]
    GATE -->|"exit 1"| FAIL["A metric is<br/>below its bar"]
    GATE -->|"exit 2"| BLIND["Nothing trustworthy<br/>to judge"]
    GATE --> ART["Report artifact<br/>agent-eval-reports"]

    classDef ok fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef warn fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    class G,TR,RG,TC,CC,DE,CJ,PASS ok;
    class FAIL,BLIND bad;
    class GATE,ART warn;
```

| Metric | Kind | Bar in the gate |
|---|---|---|
| Guardrail (allowed requests allowed, unsafe ones refused) | code, 15 tasks | all pass |
| Approval Loop (final status and revision count match the script) | code, 10 tasks | all pass |
| Routing (the expected agents ran) | code, 10 tasks | at least 80% |
| Task Completion | DeepEval, 10 tasks | average at least 0.7 |
| Plan Quality that sees trip details | custom GEval judge, 10 tasks | average at least 0.7 |
| Plan Quality and Plan Adherence (DeepEval's own versions) | DeepEval, 10 tasks | reported, **not gated** (see below) |

The gate (`.github/scripts/eval_gate.py`) exits 0 on a pass, 1 when a metric is below its bar, and 2 when there is nothing trustworthy to judge (no summary, a stub-judge summary, or a partial run). A task that errored counts as 0. The judge is OpenAI `gpt-4o-mini` with no fallbacks, so scores always come from the same model.

**First live run (3 Oct 2026, GitHub Actions, judge `gpt-4o-mini`, the real graph, flights from fixtures).** It failed the original gate, and the failure was informative. No metric errored, so these are real scores.

| Metric | First live result |
|---|---|
| Guardrail | 14 of 15 passed |
| Routing | 10 of 11 passed |
| Approval Loop | 10 of 11 passed |
| Task Completion (DeepEval) | average 0.87, 10 of 11 passed |
| Plan Quality (DeepEval) | average 0.55, 1 of 11 passed |
| Plan Adherence (DeepEval) | average 0.16, 1 of 11 passed |
| Plan Quality that sees trip details (custom judge) | average 0.95, 9 of 10 passed |

Two findings came out of it. First, one golden was labelled wrongly: a 7-day trip for 4 people on a $500 budget. The supervisor refused it as unrealistic, which is the right answer, and that one task is behind the single miss in Guardrail, Routing, Approval Loop and Task Completion. I relabelled it as a refusal, so the dataset now has 10 allowed tasks and 5 refused ones. I changed the label after seeing the result. The second run, below, confirms the effect. Second, DeepEval's own Plan Quality and Plan Adherence scored low on almost every task. The one "pass" in each row was the Tokyo task, where DeepEval found no plan in the trace and returned 1, so none of the 10 tasks with a real plan passed either metric. The judge's reasons were that the plan has no flight or hotel detail and does not mention the approval step. Yatra is a fixed graph and not a free planner, so my reading is that these two metrics measure a mismatch of shape more than the quality of the work. That is a judgement and not a proven cause. I took them out of the gate and kept them in every report. **That was my call after seeing the numbers**, so the gate was shaped with hindsight. To gate on them again, move the two names from `REPORT_ONLY` back into `RULES` in `eval_gate.py`. The custom judge's 0.95 is not comparable with them, because its rubric lists the valid agents and so asks an easier question.

**Second live run (3 Oct 2026, GitHub Actions run 37143852885, manual, commit `07a4dc0`, same judge, the revised dataset and gate).** It passed the gate. No metric errored.

| Metric | Second live result |
|---|---|
| Guardrail | 15 of 15 passed |
| Routing | 10 of 10 passed |
| Approval Loop | 10 of 10 passed |
| Task Completion (DeepEval) | average 0.965, 10 of 10 passed |
| Plan Quality (DeepEval, report only) | average 0.50, 0 of 10 passed |
| Plan Adherence (DeepEval, report only) | average 0.05, 0 of 10 passed |
| Plan Quality that sees trip details (custom judge) | average 0.976, 10 of 10 passed |

The relabel did what I expected: Tokyo is now a correct refusal, and the single misses in Guardrail, Routing, Approval Loop and Task Completion are gone. DeepEval's own plan metrics now fail on all 10 tasks that have a real plan, and the earlier "1 of 11" was the empty-plan Tokyo task, so that pass was vacuous. Read this result with care. It is one run, on a dataset and a gate that I changed after seeing the first run. It shows that the revised version agrees with itself, not that the agent would have met a gate fixed in advance, and the spread between runs is unknown.

**Verified:** the real graph and the real DeepEval iterator end to end with a live judge (two scored runs, and the second one passed the revised gate), the gate's three exit codes, and 74 key-free tests of the plumbing. An earlier manual run failed before scoring, for two bugs that are fixed: an API key saved with a trailing newline, and goldens with 2099 dates that the supervisor refused. **Not verified:** that the gate passes again on a second run (the spread between runs is unknown, and the dataset and rules were revised after the first run), the fallback chain against real providers (real model calls went through it, but the logs do not record which model answered, so a switch to the OpenAI fallback was never observed), whether the custom judge separates good plans from bad ones (`python -m evals.check_plan_judge`), and any latency or cost figure. Details are in [`specs/07-evals.spec.md`](specs/07-evals.spec.md), section 8.

---

## Deployment and operations

### Where it runs

```mermaid
flowchart TB
    BR([Visitor browser]) --> PAGE

    subgraph LIVE["LIVE: Streamlit Community Cloud, deployed by hand"]
        direction TB
        SEC["Secrets box<br/>keys never in the repo"]
        subgraph PROC["One app process"]
            PAGE["Streamlit page"] --> LOOP["Background<br/>asyncio loop"]
            LOOP --> GR["LangGraph<br/>InMemorySaver"]
            GR -->|"stdio"| MCPS["MCP servers<br/>flights ready, weather ready<br/>hotels skipped, no Tavily key"]
        end
        SEC --> PROC
    end

    GR --> LLM["DeepSeek API<br/>OpenAI API as fallback"]
    MCPS --> OM["Open-Meteo<br/>weather"]

    subgraph LOCAL["LOCAL and CI: docker compose"]
        direction TB
        API["api :8000<br/>curl /health every 30 s<br/>restart unless-stopped"] -->|"depends_on<br/>service_healthy"| PGD[("postgres:15-alpine :5432<br/>pg_isready check")]
    end

    subgraph PLAN["PLANNED, not deployed"]
        direction TB
        RND["Render Blueprint, render.yaml<br/>API did not come up"] ~~~ VCL["Vercel or similar<br/>Next.js frontend"]
    end

    LLM ~~~ LOCAL
    OM ~~~ LOCAL
    LOCAL ~~~ PLAN

    classDef live fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef planned fill:#f3e5f5,stroke:#6a1b9a,color:#38006b,stroke-dasharray: 4 3;
    class PAGE,LOOP,GR,MCPS,SEC,LLM,OM live;
    class API,PGD,RND,VCL planned;
```

The API cannot run on Vercel Functions, because a plan streams for tens of seconds, keeps MCP subprocesses alive and needs a connection pool. So the API shell needs a container host and the frontend goes on a separate host. The browser would talk to the API directly, because a proxy in the middle would buffer the stream. [`render.yaml`](render.yaml) is a Render Blueprint for the API and the frontend (it reuses an existing Render PostgreSQL), and [`DEPLOYMENT.md`](DEPLOYMENT.md) has the environment variables, the order of operations and a post-deploy checklist. Two things to know before you deploy the API shell:

- The API allows only `localhost:3000` by default, so a deployed frontend needs `CORS_ORIGINS` set.
- The three MCP servers live inside the API's container, so one small web service runs four Python processes. I measured about 60 MB for each server and estimate about 290 MB in total, which is close to the 512 MB of a free Render instance. If it restarts for lack of memory, set `MCP_ENABLED=false` and the same tools run inside the API process. I have not measured memory on Streamlit Community Cloud, where the limits are between about 690 MB and 2.7 GB.

### What I can observe

| Signal | What it tells me | Limits |
|---|---|---|
| `/health` | Liveness: the process is up | Says nothing about the database |
| `/ready` | Readiness: 503 until the database answers, then `{"status":"ready"}` with each MCP server's status | API shell only |
| Docker `HEALTHCHECK` | Curls `/health` every 30 s, with a 10 s timeout, a 40 s start period and 3 retries | Liveness only |
| Compose health checks | `pg_isready` on PostgreSQL, curl `/health` on the API, `restart: unless-stopped`, and the API waits for a healthy database | Local and CI |
| Structured logs | Node names, errors, which path answered a tool call (`via`) | `trace_id` is empty in most lines. The logs do not say which model answered |
| Sidebar tool status | `ready`, `skipped: ...` or `failed: ...` per MCP server, and which keys are set | Streamlit only |
| Eval report artifact | `agent-eval-reports` from every `agent-evals` run | Pull request or manual runs only |
| `docs/BLOCKED.md` | What I knew, what I tried and what would unblock it, when I was stuck | A document, not a monitor |

**Not present:** a metrics system, alerting, a tracing backend and dashboards. If something breaks on the live app today, I find out when I look.

### Time and cost guards

| Guard | Value | Where |
|---|---|---|
| Revision cap | 3 revised drafts | `settings.mcp.max_revisions` |
| Streamlit turn limit | 300 s | `TURN_TIMEOUT_SECONDS` in [`runtime.py`](src/ui/runtime.py) |
| Streamlit runtime start-up | 120 s | `STARTUP_TIMEOUT_SECONDS` |
| LLM request | 45 s timeout, 1 retry | `LLM_REQUEST_TIMEOUT`, `LLM_MAX_RETRIES` |
| MCP call | 25 s, then the in-process tool | `settings.mcp.call_timeout` |
| MCP start | 20 s for each server | `settings.mcp.startup_timeout` |

### How failures are contained

Each row is a fault I thought about, what the code does, and where to check it.

```mermaid
flowchart LR
    subgraph FAULT["Fault"]
        direction TB
        F1["Guardrail model<br/>errors"]
        F2["MCP server down<br/>or slow"]
        F3["Primary LLM<br/>raises"]
        F4["Revision reply<br/>unusable"]
        F5["Itinerary node<br/>throws"]
        F6["Database<br/>not ready"]
        F7["Streamlit turn fails<br/>or takes over 300 s"]
    end

    subgraph HOLD["Containment"]
        direction TB
        H1["Refuse with a<br/>generic reason"]
        H2["Same tool in-process<br/>via says in-process"]
        H3["One retry, then<br/>gpt-4.1-mini"]
        H4["Keep the previous draft<br/>flag feedback not applied"]
        H5["Empty itinerary with<br/>a clear note"]
        H6["/ready returns 503<br/>start-up retries 10 times<br/>then fails fast"]
        H7["One fixed message<br/>details only in logs"]
    end

    F1 --> H1
    F2 --> H2
    F3 --> H3
    F4 --> H4
    F5 --> H5
    F6 --> H6
    F7 --> H7

    classDef bad fill:#ffebee,stroke:#c62828,color:#7f0000;
    classDef good fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    class F1,F2,F3,F4,F5,F6,F7 bad;
    class H1,H2,H3,H4,H5,H6,H7 good;
```

| Fault | What happens | Checked by |
|---|---|---|
| The guardrail model errors or returns bad JSON | The request is refused. The error is logged and the user gets a fixed message | [`test_supervisor.py`](tests/unit/test_supervisor.py) |
| An MCP server cannot start | It is recorded as `failed: ...`. The other servers carry on and the tool runs in-process | `test_a_server_that_cannot_start_is_skipped_not_fatal` in [`test_mcp_stdio.py`](tests/unit/test_mcp_stdio.py) |
| An MCP call dies or takes over 25 s | The in-process function answers, and `via` says so | `test_a_dead_server_falls_back_to_the_in_process_tool` in the same file |
| The primary model raises | One retry, then `gpt-4.1-mini` | [`test_llm_factory.py`](tests/unit/test_llm_factory.py), with fake clients only |
| A fallback model has no key | It is skipped with a warning when the chain is built | [`llm.py`](src/core/llm.py) |
| The revision reply is unusable | The previous draft is kept and the plan says the feedback was not applied | [`test_graph_execution.py`](tests/unit/test_graph_execution.py) |
| The itinerary node throws | An empty itinerary with the note "Could not generate itinerary." | [`graph.py`](src/agents/graph.py) |
| A judge errors or has no credentials | The score is `0.0`, never a pass | `TestJudgeRobustness` in [`test_evals.py`](tests/unit/test_evals.py) |
| The database is not up | `/ready` returns 503. Start-up retries, then fails fast | [`test_readiness.py`](tests/unit/test_readiness.py), [`test_startup.py`](tests/unit/test_startup.py) |
| The browser disconnects mid-run (API shell) | The run is cancelled and no plan is stored for it. The checkpoint keeps the last finished step | listed as a known limit |
| A Streamlit turn fails or takes over 300 s | One fixed message: "We could not plan this trip right now. Please try again." | [`test_ui_runtime.py`](tests/unit/test_ui_runtime.py), [`test_routes.py`](tests/unit/test_routes.py) for the API's `error` frame |
| Hotels without a `TAVILY_API_KEY` | The hotels server is not started and the plan says search is not configured | [`gateway.py`](src/tools/gateway.py) |
| The Streamlit app restarts or sleeps | In-memory plans are lost. The sidebar says so | not a bug: the design of the in-memory saver |

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

## Engineering habits

These are the habits this project is meant to show. They are habits, not a claim that the system is finished.

| Habit | Where it shows |
|---|---|
| Write down what done means before coding | 10 spec files, and `verify.sh` with three tiers |
| Make the safe behaviour the default | A guardrail that fails closed, judges that fail to `0.0`, a revision cap |
| Test against the real dependency when a mock would hide the bug | The PostgreSQL integration tests exist because of finding F0 |
| Stop when blind and write it down | `docs/BLOCKED.md` after five blind fixes |
| Say when a decision was made with hindsight | The relabelled golden and the report-only metrics, stated in the evals section |
| Keep claims no bigger than the evidence | The ladder above, the "Not verified" lists, and this README's honest status columns |
| Review your own work against its claims | The audit report, and the defects table below |

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

Smaller fixes landed with their own tests: hotel search through Tavily, weather through Open-Meteo (with a fallback to last year's conditions for far-future dates), the budget label wording, a stale-approval bug on re-plan, structured log fields, and `postgres://` and `PORT` handling for hosting platforms. When I built the Streamlit shell I also fixed an accidental approval: Ctrl+Enter in the feedback box submitted the approve button, so the decision controls are now plain widgets.

---

## Engineering decisions and trade-offs

| Decision | Why | Trade-off I accepted |
|---|---|---|
| Spec first, code second (10 spec files in `specs/`) | A spec gives the tests and the reviewer something fixed to check against | Specs drift. Some numbers in them are targets, not measurements |
| Guardrail fails **closed** | A safety layer that fails open is decoration | Some valid requests are rejected when the guardrail model has a bad moment |
| Judges fail with score **0.0** | A broken judge must never look like a pass | A flaky judge shows up as a failing gate, which is annoying but honest |
| Parallel research wave, budget after it | Flight, hotel and weather are independent, so wall-clock time is the slowest one, not the sum. Budget needs the flight price | Needs a typed shared state and careful merge rules |
| Human approval as `interrupt()` plus a checkpoint, not a flag in a table | The run really stops and can be resumed. With PostgreSQL it survives a restart. A stored flag would only be a record of a decision that nothing waits for | The checkpointer needs its own connection pool, and the graph must be built with it |
| A revision cap of 3 | An open-ended loop is an open-ended bill. After 3 revisions the last draft is kept and labelled as not approved | A person who wants a fourth change has to start a new request |
| Tools as MCP servers, with an in-process fallback | The tools are separate processes with their own failure and timeout, and any MCP client can use them. A server that is down does not take the plan down | Three extra processes and about 180 MB of memory. A subprocess is not counted by the coverage tool |
| MCP servers get only the keys they need | A tool process should not see the database URL or the LLM keys | Each server's environment is listed explicitly in [`gateway.py`](src/tools/gateway.py) |
| SSE rather than WebSockets | One-way streaming is all the UI needs, it works through proxies and is simple to test. The approval answer is a normal `PUT` whose response is itself a stream | No client-to-server messages on the same channel |
| Browser calls the API directly | A Next.js proxy would buffer the stream and defeat SSE | CORS must be configured per deployment |
| DeepSeek for agents, OpenAI as the fallback and for judges | The judge should not grade its own family. DeepSeek is cheap for high-volume agent calls. If it fails, the same call moves to `gpt-4.1-mini`, so a provider outage does not end the trip. Judges never fall back, so their scores stay comparable | Two providers, two keys, two failure modes. A failover can add about 90 seconds to one request in the worst case (45 second timeout, one retry). A small `LLMFactory` hides it |
| Real PostgreSQL in integration tests | Mocks would have hidden F0 | Tests need a database. CI provides one as a service |
| Template first draft, LLM only for revisions | The first draft is predictable and testable, and a revision only touches words, so the facts stay correct | The first draft is not yet "intelligent". See roadmap M4 |
| A second shell (Streamlit) over the same core | The API shell needs a container host, a database and a frontend host. Streamlit runs the graph in one process, so it could go online in one step | In-memory plans, no login, and a background-loop bridge to maintain |
| The Streamlit decision controls are plain widgets | A form would let Ctrl+Enter in the feedback box approve the plan by accident | A few more reruns of the page |

---

## What is real and what is roadmap

| Capability | Status | Evidence |
|---|---|---|
| Supervisor guardrail with fail-closed JSON verdict | **Working** | [`supervisor.py`](src/agents/supervisor.py) |
| Parallel research wave, typed state, budget after research | **Working** | [`graph.py`](src/agents/graph.py), [`routing.py`](src/agents/routing.py) |
| Human approval: pause, resume, revise, cap | **Working.** Tested in unit tests (in-memory saver) and in integration tests (PostgreSQL saver), including a restart while paused | [`graph.py`](src/agents/graph.py), [`approval.py`](src/api/routes/approval.py) |
| PostgreSQL checkpointer | **Working.** `AsyncPostgresSaver` with its own connection pool | [`saver.py`](src/memory/saver.py), [`runtime.py`](src/agents/runtime.py) |
| MCP tool servers | **Working.** A real stdio server is started and called in tests. Fallback to in-process tools is tested too. On the live app, flights and weather show `ready` | [`src/mcp_servers/`](src/mcp_servers), [`gateway.py`](src/tools/gateway.py), [`test_mcp_stdio.py`](tests/unit/test_mcp_stdio.py) |
| Hotel search through Tavily | **Tested against mocked HTTP.** Needs a `TAVILY_API_KEY`. Without one the hotels server is not started and the plan says search is not configured. **Off on the live app today** | [`src/tools/`](src/tools/__init__.py), [`test_tools.py`](tests/unit/test_tools.py) |
| Weather through Open-Meteo | **Tested against mocked HTTP.** No key needed. The live app shows the weather server `ready`, but I have not recorded a live forecast | same |
| Flight search | **Mock data**, labelled `"source": "mock"`. The MCP server is real, the fares are not | [`flights.py`](src/mcp_servers/flights.py) |
| Itinerary | **First draft is a template**: one entry per day with real dates, and hotel neighbourhoods from a fixed list. **Revisions after feedback are written by the model**, limited to the activity text | [`graph.py`](src/agents/graph.py) |
| Budget | Flight cost is checked against your budget. The split across other categories is a **rule of thumb** | [`graph.py`](src/agents/graph.py) |
| SSE streaming API | **Working**, including the approval resume | [`planning.py`](src/api/routes/planning.py), [`streaming.py`](src/api/streaming.py) |
| PostgreSQL thread and message memory | **Working**, tested on real PostgreSQL | [`threads.py`](src/memory/threads.py) |
| Three-judge eval layer | **Implemented and unit-tested.** Not in the request path | [`gate.py`](src/evals/gate.py) |
| DeepEval agent evals and the merge gate | **Built and wired into CI** (`agent-evals`). The plumbing is verified with a stub judge and 74 tests. **Two live runs exist** (3 Oct 2026): the first failed the original gate, one golden was mislabelled and two DeepEval plan metrics were made report only, and the second passed the revised gate (see the evals section). The secrets exist, and the job skips (green) only if they are missing. It blocks a merge only after the job is made a required status check | [`evals/`](evals), [`eval_gate.py`](.github/scripts/eval_gate.py), [`ci.yml`](.github/workflows/ci.yml) |
| Model fallback chain | **Implemented and tested with fake clients.** The live eval runs made real model calls through it, but the logs do not record which model answered, so a switch to the OpenAI fallback was never observed. `deepseek-flash` comes from DeepSeek's documentation | [`llm.py`](src/core/llm.py) |
| Next.js frontend | **Working.** Verified in a browser against a faked LLM, supervisor and network tools, with the real graph, stream and checkpointer behind it. There are no automated frontend tests | [`frontend/`](frontend) |
| Real LLM run, end to end | **Partly.** The two live eval runs drove the real graph with real model calls and a scripted traveller. **A plan driven by a person in a browser with real keys is not recorded yet**, on the live URL or locally | [`evals/`](evals) |
| Docker image | **Built in CI**: the `build` job and `Verify` Tier 1 are green. **Not built on my machine** | [`Dockerfile`](Dockerfile), [`verify.yml`](.github/workflows/verify.yml) |
| Streamlit app | **Live on Streamlit Community Cloud**, deployed by me. Checked on 4 October 2026 by loading the page only: models listed, keys set, flights and weather ready, hotels skipped. Also driven in a browser with a stub model behind the real graph (plan, live progress, approve, three revisions, the revision-limit message, an off-topic refusal), and covered by 95 tests. **Not recorded: a full plan on the live URL.** Plans are kept in memory only | [`src/ui/`](src/ui), [`streamlit_app.py`](streamlit_app.py) |
| Public deployment of the API and Next.js shell | **None.** A Render Blueprint ([`render.yaml`](render.yaml)) exists, but the API deploy on Render did not come up and I did not find out why. Server-Sent Events on Render's free tier are untested | [`DEPLOYMENT.md`](DEPLOYMENT.md) |
| Measured latency and cost per trip | **Not measured.** The `< 10 s` and `< $0.50` figures in the specs are targets. The 290 MB memory figure is an estimate from about 60 MB per measured server | [`specs/00-overview.spec.md`](specs/00-overview.spec.md) |

### Smaller known limits

- `trace_id` is empty in most log lines, because request-level tracing is not wired in yet.
- `settings.database.pool_size` is read but unused. The pool size is fixed at 2 to 20 connections.
- There is no login. A `user_id` is only a label sent by the client (on Streamlit it is `streamlit-` plus 8 hex characters per browser session).
- The guard that stops two runs on one thread is per process, which fits a single API instance. Running several instances needs a shared lock.
- If the browser disconnects in the middle of a run, the run is cancelled and no plan is stored for it. The checkpoint keeps the last finished step.
- `delete_thread` removes only the thread row. Nothing calls it yet, and the checkpoints of a deleted thread would stay.
- The test files are not type-clean under strict pyright. CI checks `src`, and `src` has 0 errors.
- Coverage of 91.30% was measured before the Streamlit code existed and has not been re-measured.

### Not in this repo

I want to be clear about what is **not** here, so nobody assumes it from the CI badges or the Dockerfile:

- No Kubernetes or Helm charts. The folder `terraform/` is an AWS stub from an early plan: it is not used and I have not reviewed it, so please do not read it as working infrastructure as code. `infra/terraform/` is empty.
- No load test and no performance numbers.
- No monitoring stack: no metrics, alerts, tracing backend or dashboards.
- No login, no per-visitor rate limit, no automated dependency scanning and no secret scanning.
- No automated browser end-to-end tests.

Kubernetes, Helm and CI-gated evals are covered in separate projects of mine, which are **not** evidence for this one: [llmops-deep-agent](https://github.com/Amith-Ganta/llmops-deep-agent) (Helm and Kubernetes, with a DeepEval gate), [banking_application_eks](https://github.com/Amith-Ganta/banking_application_eks) and [FastAPI-ML-EKS-Platform](https://github.com/Amith-Ganta/FastAPI-ML-EKS-Platform).

---

## Roadmap with exit criteria

Each milestone ends with something I can demonstrate, not just something I can say.

```mermaid
flowchart LR
    M1["M1<br/>Real approval<br/>done"] --> M2["M2<br/>Evals in the loop<br/>run live twice, gate passes"]
    M2 --> M3["M3<br/>Real tools<br/>MCP done, live flights open"]
    M3 --> M4["M4<br/>LLM first draft"]
    M4 --> M5["M5<br/>Deploy and measure<br/>Streamlit live, API open"]

    classDef done fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef part fill:#fff8e1,stroke:#f9a825,color:#6d4c00;
    classDef next fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    class M1 done;
    class M2,M3,M5 part;
    class M4 next;
```

| Milestone | What changes | Exit criterion, something I can demonstrate |
|---|---|---|
| M1 Real approval | **Done.** `interrupt()` plus the Postgres checkpointer, so the graph pauses and resumes | Tests that pause, approve and resume, reject and re-plan, hit the cap, and survive a restart while paused |
| M2 Evals in the loop | **Partly done.** The golden set, the DeepEval metrics, the gate and the CI job exist. Still open: making the job a required check, and more runs to see the spread | A deliberately bad change is blocked by CI |
| M3 Real tools | **Partly done.** The tools are MCP servers. Still open: live flight data | A plan with no mock data in it |
| M4 LLM first draft | Replace the template first draft with a model-written plan and real neighbourhood data | Judge pass rates reported with the sample size |
| M5 Deploy and measure | **Partly done.** The Streamlit shell is live. Still open: a deployed API shell, then load measurement, a spend cap and a rate limit | p50 and p95 latency and cost per trip, measured and published |

### Build history

```mermaid
timeline
    title Yatra AI build history
    section September 2026
        27 to 30 Sep : 86 commits : Specs, graph, guardrail and human approval : MCP servers, API and Next.js frontend : The review of the database and the defects table
    section October 2026
        3 Oct : DeepEval suite and model fallback : Two live eval runs, the first fails the gate and the second passes : Render attempt for the API does not come up
        4 Oct : Streamlit shell with 95 tests : I deploy it on Streamlit Community Cloud : This README rewrite
```

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

**Streamlit app** (no PostgreSQL and no Docker needed):

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then put your DEEPSEEK_API_KEY and OPENAI_API_KEY in it
streamlit run streamlit_app.py                               # http://localhost:8501
```

Keys can also come from the environment or a `.env` file. `.streamlit/secrets.toml` is git-ignored. Without a key for the main model, the page shows what is missing instead of failing later. Set `MCP_ENABLED=false` to run the tools in-process, which starts faster and uses less memory.

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
  agents/       graph.py, runtime.py, routing.py, supervisor.py, trip.py, plan.py, state.py, jsonutil.py
  api/          FastAPI app factory, SSE runner (streaming.py), routes (plan, approval, health)
  core/         config, LLM factory, telemetry, errors, startup
  evals/        gate.py and the safety, factuality and budget judges (request-time, not in the request path)
  memory/       PostgreSQL pool, threads, migrations, saver.py (the LangGraph checkpointer)
  mcp_servers/  hotels (Tavily), flights (mock), weather (Open-Meteo): one stdio MCP server each
  tools/        the tool functions, and gateway.py that calls them through MCP with a fallback
  ui/           the Streamlit app: app.py (page), views.py (plan tabs), formatting.py, runtime.py (background loop), bootstrap.py (secrets)
streamlit_app.py  entry point for Streamlit (local and Community Cloud)
.streamlit/     config.toml and secrets.toml.example (the real secrets.toml is git-ignored)
evals/          DeepEval agent evals: eval_agent.py, 15 goldens, a custom plan judge, report writer
frontend/       Next.js 15 app: home, plan, results and approve pages
specs/          10 spec files that drive the build
tests/          unit (458, of which 95 are for the Streamlit app) and integration (37) suites
docs/           AUDIT.md, BLOCKED.md and history/ (working notes from the first build night, 29 September 2026, not maintained)
.github/        workflows (ci.yml, verify.yml) and scripts/eval_gate.py
.mcp.json       the same three servers, for any MCP client such as Claude Code
requirements-eval.txt  requirements.txt plus deepeval, for the test and eval jobs
Dockerfile, docker-compose.yml  the API image (non-root, HEALTHCHECK) and the local stack with PostgreSQL
DEPLOYMENT.md   environment variables, Streamlit Community Cloud, Render, Vercel, container host, checklist
WORKING_URL.md  the live URL, when it was last checked and what was seen
render.yaml     Render Blueprint: API (Docker) and frontend (Node), on an existing PostgreSQL
verify.sh       the definition of done, in 3 tiers
terraform/      an unused AWS stub from an early plan, not reviewed (infra/terraform/ is empty)
```

---

## How this was built

The project was built spec first, with an AI coding agent in the loop and a human-written bar for what counts as done. The specs, the audit and the blocker report are the evidence of that process. The first audit found 11 issues, including a provider mix-up (DeepSeek wired through a Groq client), stub tools and stub agents. A later review found the defects in the table above. All of them are documented, and the fixes are in the history.

**Author:** Amith Ganta, [github.com/Amith-Ganta](https://github.com/Amith-Ganta)
