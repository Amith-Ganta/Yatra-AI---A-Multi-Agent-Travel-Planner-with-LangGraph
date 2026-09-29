# Yatra AI — Multi-Agent Travel Planner Specification

**Version:** 1.0-spec  
**Date:** 2026-09-29  
**Status:** Phase 1 (Spec-Driven Build)  
**Target Bar:** Senior AI engineer (3-year experience)  
**Constraint:** LOW LATENCY (< 3s per agent, < 10s total trip draft)

---

## Table of Contents

1. [Product Vision](#product-vision)
2. [System Architecture](#system-architecture)
3. [Core Workflows](#core-workflows)
4. [Agent Specifications](#agent-specifications)
5. [Data Model](#data-model)
6. [API Contracts](#api-contracts)
7. [Quality Gates](#quality-gates)
8. [Deployment & Infrastructure](#deployment--infrastructure)
9. [Implementation Roadmap](#implementation-roadmap)

---

## 1. Product Vision

**Mission:**  
Build a production-grade travel planner that uses LangGraph supervisor + MCP tool integration to draft personalized itineraries, with human-in-the-loop approval and comprehensive evaluation.

**Users:**
- Travel planners (end users)
- Travel agents (API consumers)
- Support teams (HITL approvers)

**Success Metrics:**
- Trip draft latency < 10s (< 3s per agent)
- Eval pass rate > 95% (safety, factuality, budget adherence)
- Human approval rate > 90% (first-pass quality)
- Cost per trip < $0.50 (LLM tokens)

---

## 2. System Architecture

### 2.1 High-Level Design

```
┌─────────────────┐
│   FastAPI App   │  (async, SSE, Uvicorn)
├─────────────────┤
│  User Message   │
│  + thread_id    │
└────────┬────────┘
         │
    ┌────▼────────────────────────────┐
    │  LangGraph StateGraph            │
    │  (async, PostgreSQL checkpointer)│
    │                                  │
    │  ┌──────────────────────────┐    │
    │  │ 1. Supervisor Agent      │◄───┼─── Input guardrail
    │  │ (decides routing)        │    │
    │  └───┬───────────────────┬──┘    │
    │      │                   │        │
    │   ┌──▼────┬──────┬─────┬─▼──┐    │
    │   │Flight │Hotel │Weather│Budget  │
    │   │Agent  │Agent │Agent  │Agent   │
    │   └──┬────┴──────┴─────┴──┬─┘    │
    │      │                   │        │
    │   ┌──▼───────────────────▼──┐    │
    │   │ 5. Itinerary Agent      │    │
    │   │ (draft plan)            │    │
    │   └───┬───────────────────┬─┘    │
    │       │ (interrupt)       │      │
    │   ┌───▼────────────────────▼──┐  │
    │   │ 6. Human Approval Agent   │  │ ◄── HITL
    │   │ (LangGraph interrupt)     │  │
    │   └────┬────────────────────┬──┘  │
    │        │ (resume)           │     │
    │   ┌────▼────────────────────▼──┐  │
    │   │ 7. Final Response Agent    │  │
    │   │ (revise or polish)         │  │
    │   └────┬───────────────────────┘  │
    │        │                          │
    │   ┌────▼──────────────┐           │
    │   │ Evaluation Agent   │           │
    │   │ (optional, off-line)│          │
    │   └───────────────────┘           │
    └────────┬───────────────────────────┘
             │
      ┌──────▼──────┐
      │  PostgreSQL │  (thread state, messages, evals)
      ├──────────────┤
      │  Checkpoints │
      └──────────────┘
```

### 2.2 Components

| Component | Tech | Purpose |
|-----------|------|---------|
| **FastAPI + Uvicorn** | Python 3.11+ | Async HTTP + SSE streaming |
| **LangGraph** | Python | Agent orchestration + interrupt/resume |
| **MCP** | Protocol | Tool integration (Tavily, AviationStack, OpenWeatherMap) |
| **PostgreSQL** | DB | State checkpointing + long-term memory |
| **Groq ChatGroq** | LLM | Primary runtime (cheap, fast) |
| **OpenAI gpt-4o-mini** | LLM | Fallback + eval judge |
| **Pydantic** | Python | Structured outputs + validation |
| **Docker + Compose** | DevOps | Containerization + local dev parity |
| **Terraform** | IaC | AWS/GCP infrastructure (future) |
| **GitHub Actions** | CI | Test + eval gate (fails if skipped) |

### 2.3 Data Flow

1. **User submits trip query** → POST /api/travel { message, thread_id? }
2. **App loads or creates thread** from PostgreSQL
3. **Graph invokes supervisor** with guardrail check
4. **Supervisor selects agents** + extracts constraints (JSON)
5. **Agents run in order** (flight → hotel → weather → budget → itinerary)
6. **Itinerary drafted** → `interrupt()` pauses graph
7. **App returns draft** to user
8. **User approves or revises** → POST /api/travel/approve { approved, feedback? }
9. **App resumes graph** with `Command(resume=...)`
10. **Final response agent** polishes or revises
11. **App streams result** via SSE
12. **Eval suite** (async, offline) scores thread on safety, factuality, cost

---

## 3. Core Workflows

### 3.1 Draft Trip

**Trigger:** User submits prompt  
**Flow:**

```
User Prompt
    ↓
Supervisor (guardrail check)
    ↓ (allowed=true)
Flight Agent (MCP: AviationStack)
    ↓
Hotel Agent (MCP: Tavily search)
    ↓
Weather Agent (MCP: OpenWeatherMap)
    ↓
Budget Agent (LLM calculation)
    ↓
Itinerary Agent (LLM draft)
    ↓
[interrupt()]
    ↓
Draft returned to user
```

**Expected latency:**
- Supervisor: < 1s
- Flight: < 2s (MCP call)
- Hotel: < 2s (MCP call)
- Weather: < 1s (MCP call)
- Budget: < 1s (LLM)
- Itinerary: < 2s (LLM)
- **Total: < 10s**

### 3.2 Approve & Finalize

**Trigger:** User clicks "Approve" or "Request Revision"  
**Flow:**

```
User feedback { approved, feedback? }
    ↓
[resume(feedback)]
    ↓
Final Response Agent
    ↓ (if approved=true)
Polish & format
    ↓
Return final trip plan
    ↓
Store in PostgreSQL
```

### 3.3 Evaluate (Async, Post-Production)

**Trigger:** Background job, scheduled or on-demand  
**Flow:**

```
Query PostgreSQL for unevaluated threads
    ↓
For each thread:
  - Run JSON structure eval (LLM)
  - Run factuality eval (LLM + data)
  - Run cost eval (token count)
  - Run safety eval (guardrail check)
    ↓
Store scores in PostgreSQL
    ↓
Alert if any < threshold
```

---

## 4. Agent Specifications

### 4.1 Supervisor Agent

**Input:** User message + trip constraints (user-provided)  
**Output:** JSON { allowed: bool, reason: str, selected_agents: [str], constraints: {...} }

**Guardrail Check:**
- Is this a valid travel-planning request? (Yes/No)
- Extract trip type: leisure, business, adventure, etc.
- Extract date range, budget, party size.

**Routing Logic:**
- Always run: flight, itinerary, final_response.
- Conditionally run: hotel (if trip > 1 day), weather (if >1 week), budget (if budget mentioned).

**Latency SLA:** < 1s

**LLM:** deepseek:deepseek-chat (primary)

### 4.2–4.5 Specialist Agents (Flight, Hotel, Weather, Budget)

#### Flight Agent
- **Input:** Trip constraints (dates, party size, budget)
- **Output:** JSON { flights: [...], airlines: [...], best_option: {...}, advice: str }
- **MCP:** AviationStack
- **Latency SLA:** < 2s
- **LLM:** deepseek:deepseek-chat

#### Hotel Agent
- **Input:** Destination, dates, budget, preferences
- **Output:** JSON { hotels: [...], neighborhoods: [...], recommendations: str }
- **MCP:** Tavily (web search)
- **Latency SLA:** < 2s
- **LLM:** deepseek:deepseek-chat

#### Weather Agent
- **Input:** Destination, dates
- **Output:** JSON { current: {...}, forecast: [...], packing_advice: str }
- **MCP:** OpenWeatherMap
- **Latency SLA:** < 1s
- **LLM:** (LLM optional; mostly MCP data)

#### Budget Agent
- **Input:** All prior agent outputs
- **Output:** JSON { categories: {...}, total_estimate: float, savings: [...], feasibility: bool, advice: str }
- **MCP:** None (LLM + calculation)
- **Latency SLA:** < 1s
- **LLM:** deepseek:deepseek-chat

### 4.6 Itinerary Agent

**Input:** All prior outputs  
**Output:** JSON { itinerary: [day1: {...}, day2: {...}, ...], highlights: [...], notes: str }

**Logic:**
- Build day-by-day schedule respecting flights, hotels, weather.
- Suggest attractions, restaurants, activities.
- Balance rest, activities, budget.

**Latency SLA:** < 2s  
**LLM:** deepseek:deepseek-chat

### 4.7 Human Approval Agent

**Input:** Drafted itinerary  
**Action:** `interrupt()` pauses graph

**Resume Payload:** { approved: bool, feedback: str? }

**Logic:**
- Approval: signal final_response to polish.
- Revision: return feedback to itinerary agent for re-drafting.

**Latency SLA:** Blocking (user-driven)

### 4.8 Final Response Agent

**Input:** Drafted itinerary + approval decision + feedback (if any)  
**Output:** JSON { final_plan: {...}, summary: str, share_url: str? }

**Logic:**
- If approved: Polish formatting, add packing list, tips.
- If revision requested: Re-draft itinerary with feedback, repeat approval.

**Latency SLA:** < 2s  
**LLM:** deepseek:deepseek-chat

### 4.9 Evaluation Agent (Async, Off-Line)

**Runs:** Post-production, via background job  
**Input:** Completed thread from PostgreSQL  
**Output:** JSON { safety_score, factuality_score, budget_adherence, cost_usd, passed: bool }

**Evals:**
- **Safety:** No harmful content, PII masked.
- **Factuality:** Flights/hotels/weather data matches real data.
- **Budget:** Estimated cost ≤ user budget + 10%.
- **Cost:** Token count, API calls, total cost.

**LLM (Judge):** openai:gpt-4o-mini (primary), openai:gpt-4.1-mini (secondary)

---

## 5. Data Model

### 5.1 TravelState (TypedDict)

```python
class TravelState(TypedDict):
    # Input
    message: str                       # User query
    thread_id: str                     # For resumption
    
    # Supervisor output
    allowed: bool
    reason: str
    selected_agents: list[str]
    trip_constraints: dict
    
    # Agent outputs
    flight_output: dict | None
    hotel_output: dict | None
    weather_output: dict | None
    budget_output: dict | None
    itinerary_output: dict | None
    
    # HITL
    human_approval: bool | None
    feedback: str | None
    
    # Final
    final_response: dict
    
    # Metadata
    created_at: str
    updated_at: str
    user_id: str
    model_used: str
    total_tokens: int
    cost_usd: float
    
    # Evaluation
    eval_scores: dict | None
    eval_passed: bool | None
```

### 5.2 PostgreSQL Schema

```sql
CREATE TABLE threads (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  status ENUM ('draft', 'approved', 'final', 'archived'),
  state JSONB NOT NULL,  -- Full TravelState
  PRIMARY KEY (id)
);

CREATE TABLE checkpoints (
  id SERIAL PRIMARY KEY,
  thread_id UUID NOT NULL REFERENCES threads(id),
  checkpoint_id TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (thread_id, checkpoint_id)
);

CREATE TABLE evaluations (
  id SERIAL PRIMARY KEY,
  thread_id UUID NOT NULL REFERENCES threads(id),
  safety_score FLOAT,
  factuality_score FLOAT,
  budget_adherence_score FLOAT,
  cost_usd FLOAT,
  passed BOOLEAN,
  evaluated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 6. API Contracts

### 6.1 POST /api/travel

**Request:**
```json
{
  "message": "Plan a 5-day trip to Japan for 2 people, $3000 budget, March 2025",
  "thread_id": "optional-uuid"
}
```

**Response (202 Accepted - SSE stream):**
```json
{
  "thread_id": "uuid",
  "status": "draft",
  "draft": {...}  // streamed
}
```

### 6.2 POST /api/travel/approve

**Request:**
```json
{
  "thread_id": "uuid",
  "approved": true,
  "feedback": "optional revision notes"
}
```

**Response (202 Accepted - SSE stream):**
```json
{
  "thread_id": "uuid",
  "status": "final",
  "final_plan": {...}  // streamed
}
```

### 6.3 GET /api/travel/{thread_id}

**Response:**
```json
{
  "thread_id": "uuid",
  "status": "final",
  "state": {...},
  "eval_scores": {...},
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### 6.4 GET /health

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "features": ["supervisor", "mcp", "hitl", "evals"]
}
```

---

## 7. Quality Gates

### 7.1 Latency Gate

| Component | SLA | Tolerance |
|-----------|-----|-----------|
| Supervisor | < 1s | 1.5s |
| Flight Agent | < 2s | 3s |
| Hotel Agent | < 2s | 3s |
| Weather Agent | < 1s | 1.5s |
| Budget Agent | < 1s | 1.5s |
| Itinerary Agent | < 2s | 3s |
| **Total Trip Draft** | **< 10s** | **15s** |

### 7.2 Eval Gate (CI/CD)

**PR Blocks if:**
- Any eval run is skipped.
- Safety score < 95%.
- Factuality score < 90%.
- Budget adherence < 95%.
- Cost per trip > $0.50.

**Eval Coverage:** ≥ 50 example trips (manual dataset) + 10 random production threads.

### 7.3 Code Quality Gate

- Linting (ruff) must pass.
- Type checking (pyright) must pass.
- Test coverage ≥ 80%.
- No secrets in code (git-secrets).

---

## 8. Deployment & Infrastructure

### 8.1 Local Development

**Docker Compose:**
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: yatra
      POSTGRES_PASSWORD: dev
    ports:
      - "5432:5432"

  yatra-api:
    build: .
    environment:
      DATABASE_URL: postgresql://...
      GROQ_API_KEY: ...
    ports:
      - "8000:8000"
    depends_on:
      - postgres

  mcp-weather:
    build: ./servers/weather
    ports:
      - "9001:8000"
```

### 8.2 Production Deployment (Terraform)

**Target:** AWS (ECS) or GCP (Cloud Run)

**Infrastructure:**
- PostgreSQL (RDS or Cloud SQL)
- FastAPI (ECS or Cloud Run)
- MCP servers (sidecar or separate)
- CloudFront + S3 (frontend)
- GitHub Actions (CI/CD)

---

## 9. Implementation Roadmap

### Phase 1 (NIGHT MODE — Spec-Driven)
- [x] Delete legacy code
- [x] Create directory structure
- [x] Write REFERENCE_ANALYSIS.md
- [x] Write 00-overview.spec.md
- [ ] Create .gitignore
- [ ] Write BUILD_PLAN.md
- [ ] Open PR

### Phase 2 (Config + ML models)
- [ ] src/config.py (Groq, OpenAI, env loading)
- [ ] .mcp.json (MCP server config)
- [ ] specs/01-config.spec.md

### Phase 3 (Agents)
- [ ] src/agents/supervisor.py
- [ ] src/agents/flight.py
- [ ] src/agents/hotel.py
- [ ] src/agents/weather.py
- [ ] src/agents/budget.py
- [ ] src/agents/itinerary.py
- [ ] src/agents/approval.py
- [ ] src/agents/final_response.py
- [ ] specs/02-agents.spec.md

### Phase 4 (Tools + MCP)
- [ ] src/tools/mcp_client.py
- [ ] servers/weather_mcp.py
- [ ] specs/03-tools-mcp.spec.md

### Phase 5 (Memory + State)
- [ ] src/memory/postgres_checkpoint.py
- [ ] src/state.py (TravelState)
- [ ] specs/04-memory.spec.md

### Phase 6 (API)
- [ ] src/api/app.py (FastAPI)
- [ ] src/api/routes.py
- [ ] specs/05-api.spec.md

### Phase 7 (Tests)
- [ ] tests/unit/test_agents.py
- [ ] tests/integration/test_workflows.py
- [ ] specs/06-tests.spec.md

### Phase 8 (Evals — CENTERPIECE)
- [ ] evals/datasets/trips.json (50+ examples)
- [ ] evals/judges/safety_judge.py
- [ ] evals/judges/factuality_judge.py
- [ ] evals/judges/budget_judge.py
- [ ] evals/judges/cost_judge.py
- [ ] evals/run_evals.py
- [ ] evals/eval_report.json
- [ ] specs/07-evals.spec.md

### Phase 9 (HITL Gate)
- [ ] src/api/approval.py
- [ ] src/api/hitl_store.py
- [ ] Frontend JS for approval form
- [ ] specs/08-hitl.spec.md

### Phase 10 (Containers)
- [ ] Dockerfile
- [ ] docker-compose.yml
- [ ] specs/09-containers.spec.md

### Phase 11 (CI/CD)
- [ ] .github/workflows/test.yml
- [ ] .github/workflows/evals.yml
- [ ] specs/10-ci.spec.md

### Phase 12 (Terraform)
- [ ] infra/main.tf
- [ ] infra/variables.tf
- [ ] specs/11-terraform.spec.md

### Phase 13 (Claude Tooling)
- [ ] CLAUDE.md
- [ ] .claude/rules/*.md
- [ ] .claude/commands/*.md
- [ ] .claude/agents/*.md
- [ ] .claude/skills/deploy/SKILL.md
- [ ] specs/12-claude-tooling.spec.md

---

## Appendix A: Model Policy (STRICT)

**Runtime:**
- Primary: `deepseek:deepseek-chat`
- Fallback: `openai:gpt-4o-mini`

**Eval Judges:**
- Primary: `openai:gpt-4o-mini`
- Secondary: `openai:gpt-4.1-mini`
- Fallback: `deepseek:deepseek-chat`

**FORBIDDEN:**
- gpt-4.1, gpt-4, gpt-4-turbo, gpt-5.*
- claude-* (all versions)

**Rationale:** Cost, latency, reproducibility.

---

## Appendix B: Conventions

### Commit Format (Conventional Commits)

```
<type>(<scope>): <description>

<body>

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01E36RmCwPd6Y4vLwW9s9yZ1
```

**Types:** feat, fix, docs, chore, refactor, perf, test, build, ci, style, revert

### Python Style

- Black formatter (88 chars)
- Type hints everywhere (Pydantic + TypedDict)
- No secrets in code (.env only)
- Async first (FastAPI, asyncio)

### File Naming

- Agents: `src/agents/{name}.py`
- Tools: `src/tools/{name}.py`
- Tests: `tests/{unit|integration}/{feature}_test.py`
- Specs: `specs/{NN}-{name}.spec.md`

---

**End of Specification v1.0**  
**Next Phase:** 02-config.spec.md (Phase 2)
