# Reference Analysis: Multi-Agent Travel Planning Systems

**Date:** 2026-09-29  
**Purpose:** Study three production-grade LangGraph + MCP travel planning systems to inform Yatra AI rebuild.

---

## Repo 1: entbappy/Multi-Agent-System-using-LangGraph-MCP-Supervisor-Guardrails-HITL

**URL:** https://github.com/entbappy/Multi-Agent-System-using-LangGraph-MCP-Supervisor-Guardrails-HITL

### Key Architecture Patterns

| Component | Pattern |
|-----------|---------|
| **Framework** | FastAPI (async, SSE-ready) |
| **Graph** | LangGraph StateGraph with supervisor routing |
| **Guardrails** | Input validation before supervisor dispatch |
| **HITL** | Interrupt + resume via thread_id + API endpoint |
| **MCP** | Custom weather server (example adapter) |
| **Concurrency** | nest_asyncio for sync wrappers in async context |

### File Structure (Key Files)

```
app.py                              # FastAPI endpoints + web UI
backend.py                          # Agent orchestration (sync wrappers)
mcp_client.py                       # MCP client helpers
custom_weather_mcp_server.py        # Example FastMCP server
templates/, static/                 # Frontend (HTML/CSS/JS)
requirements.txt
```

### Core Insights

1. **FastAPI + Uvicorn** for low-latency async serving.
2. **nest_asyncio** pattern allows sync orchestration code to call async MCP helpers.
3. **Interrupt + resume** via LangGraph's `interrupt()` and `thread_id` for HITL.
4. **Single supervisor** decides which agents run; no separate guardrail agent.
5. **No database** — state is in-memory; for production, add Postgres checkpointer.
6. **No evals** — suggests user should add evaluation suite.
7. **Minimal MCP example** — only weather server; real system needs more.

### What to Borrow

- FastAPI architecture (async, SSE-ready).
- Supervisor-only routing (no separate guardrail agent).
- nest_asyncio pattern for sync wrappers.
- HITL via `interrupt()` + thread_id.

### What to Improve

- Add PostgreSQL checkpointing for thread resumption.
- No comprehensive evaluation suite.
- No Docker/deployment infrastructure.
- No CI/CD or testing framework.

---

## Repo 2: codewithaarohi/Multi_agent_system_part_5

**URL:** https://github.com/codewithaarohi/Multi_agent_system_part_5

### Key Architecture Patterns

| Component | Pattern |
|-----------|---------|
| **Framework** | Streamlit (simple, interactive UI) |
| **Graph** | LangGraph StateGraph with supervisor + 7 specialist agents |
| **Agents** | flight, hotel, weather, budget, itinerary + human_approval + final_response |
| **Guardrails** | LLM-based validation in supervisor (JSON checks) |
| **HITL** | LangGraph `interrupt()` + `Command(resume=...)` |
| **MCP** | Three servers (AviationStack, Tavily, OpenWeatherMap) |
| **Memory** | PostgreSQL checkpointer via LangGraph |
| **LLM** | ChatGroq (llama-3.3-70b, **NOT GPT-4**) |
| **Deployment** | Docker + Docker Compose |

### File Structure (Key Files)

```
graph.py                            # StateGraph + checkpointer setup
agents.py                           # Eight node functions (supervisor through final_response)
state.py                            # TravelState TypedDict
config.py                           # Env loading, LLM factory
mcp_client.py                       # MultiServerMCPClient
weather_mcp_server.py               # Local FastMCP (OpenWeatherMap)
aviationstack-mcp/                  # Vendored MCP server
frontend.py                         # Streamlit UI
requirements.txt
.env                                # Secrets (API keys, DB URL)
```

### Core Insights

1. **Supervisor agent** decides which agents run + returns constraints as JSON.
2. **Agent routing** follows `AGENT_ORDER` (flight → hotel → weather → budget → itinerary).
3. **Guardrail is LLM-based**: supervisor checks if request is valid travel-planning.
4. **Seven specialist agents** (not monolithic); each has a clear MCP responsibility.
5. **PostgreSQL checkpointing** allows thread resumption with `Command(resume=...)`.
6. **Interrupt + resume** well-documented; human approval pauses graph.
7. **Three MCP servers**: two vendored (AviationStack, Tavily), one custom (weather).
8. **Streamlit frontend** for quick prototyping; not production-grade.
9. **Groq ChatGroq** as LLM (cheap, fast); **NOT Claude, GPT-4, or OpenAI**.
10. **No evaluation suite** — suggests this is a gap in the ecosystem.

### What to Borrow

- **Eight-agent architecture**: supervisor → 4 specialists → itinerary → human_approval → final_response.
- **Supervisor returns JSON**: `{"allowed": bool, "reason": str, "selected_agents": [...], "constraints": {...}}`.
- **PostgreSQL checkpointer** pattern for thread resumption.
- **Agent routing via `AGENT_ORDER`** — elegant skip pattern.
- **MCP vendoring strategy** (keep problematic servers in-tree).
- **Groq as LLM** (cost + latency advantage).
- **Interrupt + resume flow** with `Command(resume=...)`.

### What to Improve

- **Streamlit → FastAPI** for production-grade API.
- **Add comprehensive evaluation suite** (JSON quality, safety, cost).
- **Add Docker CI/CD** (GitHub Actions that fail if evals < threshold).
- **Add Terraform** for infrastructure.
- **LLM-based guardrail → two-tier**: syntactic check + semantic check.
- **Structured outputs** (Pydantic models) for robustness.

---

## Repo 3: Amith-Ganta/spendly-render-deploy

**URL:** https://github.com/Amith-Ganta/spendly-render-deploy

### Key Architecture Patterns

| Component | Pattern |
|-----------|---------|
| **Framework** | Flask (simple, sync) |
| **Database** | SQLite with parameterized queries |
| **Testing** | Pytest with 47 tests, CI-ready |
| **Deployment** | Render (cloud) |
| **Dev Process** | Systematic, test-driven, documented |

### File Structure

```
app.py                              # All Flask routes
database/
  db.py                             # Schema + migrations
  queries.py                        # Read-side helpers
templates/                          # Jinja2 templates
static/                             # CSS + vanilla JS
tests/                              # 47 Pytest tests (comprehensive)
requirements.txt
```

### Core Insights

1. **Highly documented development process** (2-month journey with phase breakdowns).
2. **Test-driven**: 47 comprehensive Pytest tests (CI-ready).
3. **Parameterized SQL queries** for security.
4. **Vanilla JavaScript** (no frameworks) for simplicity.
5. **Session-based auth** with werkzeug password hashing.
6. **Mobile-first CSS design system** with variables.
7. **Documented in Claude Code** (AI pair programming).
8. **Production-ready on Render** (real deployment experience).

### What to Borrow

- **Test-driven process** (write tests first, then implementation).
- **Comprehensive test suite** (47 tests, well-organized).
- **CI-ready mindset** (tests must pass, coverage tracked).
- **Documented development phases** (step-by-step journal).
- **Vanilla tech stack** (no bleeding-edge frameworks).
- **Parameterized SQL** for safety.
- **Design system variables** (CSS, easily swappable).

### What NOT to Borrow

- **Flask** (use FastAPI for async, SSE, low latency).
- **SQLite** (use PostgreSQL for distributed checkpointing).
- **Simple authentication** (travel planner has higher stakes).

---

## Synthesis: Yatra AI Architecture

### Lessons Learned

1. **FastAPI + Async** (from Repo 1): Low latency, SSE-ready.
2. **PostgreSQL checkpointing** (from Repo 2): Thread resumption, production grade.
3. **Eight-agent structure** (from Repo 2): Supervisor → specialists → approval → final.
4. **Groq as LLM** (from Repo 2): Cost + latency wins.
5. **Test-driven development** (from Repo 3): Comprehensive eval suite from day 1.
6. **Documented phases** (from Repo 3): Journal for transparency.

### Yatra AI Design Decisions

| Decision | Rationale |
|----------|-----------|
| **FastAPI + Uvicorn** | Low latency, async, SSE streaming |
| **PostgreSQL** | Checkpointing, distributed, production-grade |
| **Groq ChatGroq** | Cost + latency; fallback to gpt-4o-mini |
| **Eight-agent supervisor model** | Clear responsibilities, scaling path |
| **Comprehensive evals from Phase 1** | Quality gate, reproducible, CI/CD integrated |
| **Docker + Docker Compose** | Local dev, production parity |
| **GitHub Actions CI** | Fails if evals skipped or quality < threshold |
| **Terraform** | Infrastructure as code, 3-year engineering bar |
| **MCP servers** | Weather, flights, hotels, attractions (vendored if needed) |

### Model Policy (STRICT)

**Runtime:**
- `deepseek:deepseek-chat` (PRIMARY)
- `openai:gpt-4o-mini` (FALLBACK)

**Eval Judges:**
- `openai:gpt-4o-mini` (PRIMARY)
- `openai:gpt-4.1-mini` (SECONDARY)
- `deepseek:deepseek-chat` (FALLBACK)

**FORBIDDEN:**
- gpt-4.1, gpt-4, gpt-4-turbo, gpt-5.*, claude-*

**Rationale:** Cost, latency, and reproducibility across environments.

---

## Gaps & Opportunities

| Gap | Opportunity |
|-----|-------------|
| No evals in any repo | Build comprehensive evaluation suite (centerpiece of Phase 8) |
| No CI/CD that enforces quality | Add GitHub Actions that fails if evals skipped |
| No Terraform in Repo 1–2 | Add infrastructure-as-code for 3-year bar |
| No Docker in Repo 1 | Add Docker Compose for local dev + production parity |
| LLM guardrail in Repo 2 only | Expand to two-tier (syntactic + semantic) |
| No structured outputs (Pydantic) | Use TypedDict + runtime validation |
| Minimal cost tracking | Track tokens, latency per agent, cost per trip |
| No docs generation | Auto-generate agent docs from code |

---

## Next Phase

PHASE 1: Scaffold the directory structure, create `specs/00-overview.spec.md`, set up `.gitignore`, and document the build plan.
