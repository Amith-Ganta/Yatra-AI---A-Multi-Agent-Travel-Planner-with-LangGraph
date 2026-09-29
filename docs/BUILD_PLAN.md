# Yatra AI — 13-Phase Build Plan

**Version:** 1.0  
**Started:** 2026-09-29  
**Target Completion:** 2026-12-31  
**Status:** Phase 0–1 (Specs drafted, scaffolding done)

---

## Overview

This document tracks the 13-phase build to production-grade Yatra AI, a multi-agent travel planner with LangGraph, MCP, PostgreSQL, and comprehensive evaluations.

**Key Principles:**
- **Spec-first**: No code without approved spec.
- **Cheap models**: deepseek:deepseek-chat (runtime), openai:gpt-4o-mini (evals).
- **Eval-centric**: Comprehensive evals from Phase 8 → GitHub Actions gate.
- **Low latency**: Target < 10s for full trip draft.
- **Production-ready**: Docker, Terraform, CI/CD from day 1.

---

## Phase Breakdown

### Phase 0: Reference Analysis ✅

**Deliverables:**
- [x] REFERENCE_ANALYSIS.md
- [x] Study 3 production repos (entbappy, codewithaarohi, Amith-Ganta)
- [x] Extract architecture patterns + lessons

**Commits:**
- `cee5f4d`: docs(reference): add analysis of 3 reference repos

**Key Outputs:**
- FastAPI + async recommendation
- PostgreSQL checkpointing strategy
- Eight-agent supervisor model
- Comprehensive eval suite design

---

### Phase 1: Scaffold & Specs ✅

**Deliverables:**
- [x] Directory structure (specs/, src/, tests/, evals/, infra/)
- [x] specs/00-overview.spec.md (complete system spec)
- [x] .gitignore (Python/FastAPI/Docker)
- [x] BUILD_PLAN.md (this file)
- [ ] MORNING_REPORT.md (tomorrow)

**Commits:**
- `197d7d7`: chore(scaffold): create target folder tree
- `2ab3584`: docs(spec): add 00-overview.spec.md
- `323575a`: chore(git): add .gitignore
- TBD: docs: add BUILD_PLAN.md

**Key Decisions:**
- FastAPI + Uvicorn (async, SSE-ready)
- PostgreSQL + LangGraph checkpointer
- Groq ChatGroq (primary), gpt-4o-mini (fallback + judge)
- Eight-agent model (supervisor → 4 specialists → itinerary → approval → final)
- Evals as centerpiece (Phase 8)

---

### Phase 2: Config & Model Setup

**Scope:**
- src/config.py (Groq, OpenAI env loading)
- .mcp.json (MCP server configuration)
- specs/01-config.spec.md

**Owner:** TBD  
**Estimated Duration:** 1–2 days  
**Blocker:** None

**Success Criteria:**
- Config loads from .env
- LLM factory works (deepseek + fallback)
- MCP config validates

---

### Phase 3: Agents (Core Logic)

**Scope:**
- src/agents/supervisor.py (guardrail + routing)
- src/agents/flight.py (flight specialist)
- src/agents/hotel.py (hotel specialist)
- src/agents/weather.py (weather specialist)
- src/agents/budget.py (budget calculator)
- src/agents/itinerary.py (draft itinerary)
- src/agents/approval.py (human approval)
- src/agents/final_response.py (polish)
- specs/02-agents.spec.md

**Owner:** TBD  
**Estimated Duration:** 3–5 days  
**Blocker:** Phase 2 config

**Success Criteria:**
- Each agent has clear input/output spec
- Latency < 3s per agent
- Supervisor guardrail works
- All agents return Pydantic models

---

### Phase 4: Tools & MCP

**Scope:**
- src/tools/mcp_client.py (MCP client wrapper)
- servers/weather_mcp.py (local weather server)
- Integrate: AviationStack, Tavily, OpenWeatherMap
- specs/03-tools-mcp.spec.md

**Owner:** TBD  
**Estimated Duration:** 2–3 days  
**Blocker:** Phase 2 config

**Success Criteria:**
- MCP client abstracts tool calls
- Weather server runs locally
- AviationStack + Tavily + OpenWeatherMap integrated
- Tool errors handled gracefully

---

### Phase 5: Memory & State

**Scope:**
- src/state.py (TravelState TypedDict)
- src/memory/postgres_checkpoint.py (PostgreSQL checkpointer for LangGraph)
- PostgreSQL schema (threads, checkpoints, evaluations)
- specs/04-memory.spec.md

**Owner:** TBD  
**Estimated Duration:** 2–3 days  
**Blocker:** Phase 3 agents (state shape locked)

**Success Criteria:**
- TravelState validates all agent outputs
- PostgreSQL checkpointer works
- Thread resumption works
- State serialization is lossless

---

### Phase 6: API (FastAPI)

**Scope:**
- src/api/app.py (FastAPI app)
- src/api/routes.py (routes: /api/travel, /api/travel/approve, /api/travel/{id}, /health)
- SSE streaming
- specs/05-api.spec.md

**Owner:** TBD  
**Estimated Duration:** 2–3 days  
**Blocker:** Phase 3, Phase 5

**Success Criteria:**
- All routes respond
- SSE streaming works
- Error handling is robust
- CORS configured

---

### Phase 7: Tests (Unit + Integration)

**Scope:**
- tests/unit/test_agents.py (agent logic)
- tests/unit/test_mcp.py (MCP client)
- tests/unit/test_state.py (TravelState validation)
- tests/integration/test_workflows.py (end-to-end flow)
- specs/06-tests.spec.md

**Owner:** TBD  
**Estimated Duration:** 2–3 days  
**Blocker:** Phases 3–6

**Success Criteria:**
- ≥ 80% code coverage
- All workflows tested
- Mock MCP servers for tests
- CI ready (pytest in GitHub Actions)

---

### Phase 8: Evals (CENTERPIECE — CRITICAL)

**Scope:**
- evals/datasets/trips.json (50+ hand-crafted trip examples)
- evals/judges/safety_judge.py (LLM judge for PII, harmful content)
- evals/judges/factuality_judge.py (flight/hotel data matches reality)
- evals/judges/budget_judge.py (cost adherence)
- evals/judges/cost_judge.py (token count, API cost tracking)
- evals/run_evals.py (orchestrator)
- evals/eval_report.json (results)
- specs/07-evals.spec.md

**Owner:** TBD  
**Estimated Duration:** 3–5 days  
**Blocker:** Phases 6–7

**Success Criteria:**
- 50+ realistic trip examples
- Safety score ≥ 95% on dataset
- Factuality score ≥ 90%
- Budget adherence ≥ 95%
- Cost per trip tracked + reported
- Eval suite runs in < 10 min on 50 examples
- GitHub Actions gate blocks merge if eval fails

---

### Phase 9: HITL Gate (Human-in-the-Loop)

**Scope:**
- src/api/approval.py (approve/revise endpoints)
- src/api/hitl_store.py (HITL state store)
- Frontend JS: approval form, feedback capture
- specs/08-hitl.spec.md

**Owner:** TBD  
**Estimated Duration:** 1–2 days  
**Blocker:** Phase 6 (API)

**Success Criteria:**
- User can approve/reject draft
- Feedback captured
- Graph resumes with `Command(resume=...)`
- Thread state updated

---

### Phase 10: Containers (Docker)

**Scope:**
- Dockerfile (FastAPI app)
- docker-compose.yml (PostgreSQL + app + weather MCP)
- .dockerignore
- specs/09-containers.spec.md

**Owner:** TBD  
**Estimated Duration:** 1 day  
**Blocker:** Phase 6 (API complete)

**Success Criteria:**
- Local: `docker-compose up` starts full stack
- PostgreSQL accessible
- FastAPI responds
- No secrets in image

---

### Phase 11: CI/CD (GitHub Actions)

**Scope:**
- .github/workflows/test.yml (Pytest + linting)
- .github/workflows/evals.yml (Run evals, gate merge)
- .github/workflows/push-image.yml (Docker build + registry)
- specs/10-ci.spec.md

**Owner:** TBD  
**Estimated Duration:** 1–2 days  
**Blocker:** Phases 7, 8

**Success Criteria:**
- PR blocks if tests fail
- PR blocks if evals < threshold
- PR blocks if linting fails
- Merge to main publishes Docker image

---

### Phase 12: Terraform (Infrastructure)

**Scope:**
- infra/main.tf (ECS/Cloud Run)
- infra/variables.tf (environment)
- infra/rds.tf (PostgreSQL)
- infra/outputs.tf
- specs/11-terraform.spec.md

**Owner:** TBD  
**Estimated Duration:** 2–3 days  
**Blocker:** Phase 10 (Docker)

**Success Criteria:**
- Terraform plan succeeds
- Infrastructure code reviewed
- No hardcoded secrets
- Deployment to staging possible

---

### Phase 13: Claude Tooling & Docs

**Scope:**
- CLAUDE.md (repo guide)
- .claude/rules/code-style.md
- .claude/rules/testing.md
- .claude/rules/documentation.md
- .claude/commands/review.md
- .claude/commands/fix-issue.md
- .claude/agents/code-reviewer.md
- .claude/agents/security-auditor.md
- .claude/skills/deploy/SKILL.md
- specs/12-claude-tooling.spec.md

**Owner:** TBD  
**Estimated Duration:** 1–2 days  
**Blocker:** All prior phases

**Success Criteria:**
- CLAUDE.md documents everything
- New developers can onboard
- Hooks configured for validation
- Skills enable deployment automation

---

## Critical Path

```
Phase 0 → Phase 1 → Phase 2 (config)
                  ↓
            Phase 3 (agents) ←─ Phase 4 (tools) ─┐
                  ↓                               │
            Phase 5 (state) ←────────────────────┘
                  ↓
            Phase 6 (API)
                  ↓
        ┌─────────┴─────────┐
        ↓                   ↓
   Phase 7 (tests)    Phase 8 (evals) ← CENTERPIECE
        ↓                   ↓
   ─────┴─────────────────┴──── Phase 11 (CI/CD)
                ↓
        Phase 9 (HITL) → Phase 10 (Docker) → Phase 12 (Terraform)
                                                      ↓
                                              Phase 13 (Claude)
```

**Critical Path Duration:** ~20–25 days (aggressive) → 30–35 days (realistic)

---

## Metrics & Gates

### Latency Gates (Per Phase)

| Phase | Component | SLA | Tolerance | Status |
|-------|-----------|-----|-----------|--------|
| 3 | Supervisor | < 1s | 1.5s | TBD |
| 3–5 | Flight → Itinerary | < 10s | 15s | TBD |
| 8 | Eval suite (50 trips) | < 10 min | 15 min | TBD |

### Quality Gates (Phase 8+)

| Gate | Threshold | Blocker |
|------|-----------|---------|
| Safety score | ≥ 95% | YES |
| Factuality score | ≥ 90% | YES |
| Budget adherence | ≥ 95% | YES |
| Code coverage | ≥ 80% | YES |
| Linting (ruff) | 0 errors | YES |
| Type checking (pyright) | 0 errors | YES |

### Cost Gates (Phase 8)

| Metric | Target | Alert |
|--------|--------|-------|
| Cost per trip | < $0.50 | > $0.60 |
| Tokens per trip | < 2000 | > 2500 |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| LLM cost overrun | Medium | Medium | Use Groq (cheap), set token limits |
| MCP tool latency | Medium | High | Cache results, fallback to LLM-only |
| Database checkpointing issues | Low | High | Test PostgreSQL + LangGraph early (Phase 5) |
| Eval judges disagreement | Low | Medium | Use primary + secondary judges, log disagreements |
| Human approval bottleneck | Low | Low | Set SLA, escalation policy |

---

## Deliverables Summary

### Code
- src/: 8 agents + API + memory + config
- tests/: unit + integration (80% coverage)
- evals/: judges + datasets + orchestrator
- infra/: Dockerfile, docker-compose, Terraform

### Documentation
- specs/: 12 detailed specifications
- docs/: BUILD_PLAN, MORNING_REPORT, architecture diagrams
- CLAUDE.md: Developer guide + rules

### DevOps
- .github/workflows/: test, evals, deploy
- Terraform modules: app, database, networking
- Docker image: production-ready

---

## Success Criteria (MVP)

- [ ] All 13 phases complete
- [ ] All evals pass (safety, factuality, budget, cost)
- [ ] Latency < 10s for full trip draft
- [ ] 80%+ code coverage
- [ ] Docker image deployable
- [ ] GitHub Actions CI/CD green
- [ ] Terraform infrastructure reproducible
- [ ] CLAUDE.md + tooling complete
- [ ] Documentation comprehensive (no gaps)

---

## Next Steps

1. **Phase 2 kickoff:** Config setup (Groq + OpenAI)
2. **Phase 3 kickoff:** Supervisor agent (guardrail + routing)
3. **Phase 8 kickoff (CRITICAL):** Start designing eval dataset (50+ trips)
4. **Weekly standups:** Track progress, unblock risks

---

**Last Updated:** 2026-09-29  
**Owner:** Claude Haiku 4.5 (night mode)  
**Next Review:** End of Phase 2
