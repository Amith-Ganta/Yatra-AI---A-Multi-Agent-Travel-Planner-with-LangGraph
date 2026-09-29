# Claude Code Configuration

This file configures Claude Code (the AI coding assistant) for this repository.

## Project Overview

**Yatra AI** - Production-grade multi-agent travel planner with LangGraph, PostgreSQL checkpointing, and LLM-based evaluation gates.

**Architecture:**
- LangGraph supervisor + 8-agent workflow
- Async FastAPI with SSE streaming
- PostgreSQL for conversation memory
- LLM judges (safety, factuality, budget)
- 80%+ test coverage

## Development Workflow

### Branches
- `main` - Production-ready code
- `develop` - Integration branch
- `phase-*` - Feature branches (one per phase)

### Committing
Use Conventional Commits format:
```
type(scope): description

- Bullet point details
- More details

Co-Authored-By: Claude <...>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run database migrations (via docker-compose postgres)
docker-compose up -d postgres

# Run tests
pytest tests/ -v --cov=src

# Start API server
python main.py
```

## Key Files

- `src/agents/graph.py` - LangGraph supervisor + 8 agents
- `src/evals/gate.py` - Evaluation gate with judges
- `src/api/main.py` - FastAPI application factory
- `src/memory/db.py` - PostgreSQL connection pool
- `specs/` - Comprehensive phase specifications

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest --cov=src --cov-report=html

# Specific test
pytest tests/unit/test_agents.py::test_graph_builds -v
```

## Deployment

### Docker
```bash
docker-compose up --build
```

### Terraform (AWS)
```bash
cd terraform/
terraform init
terraform plan
terraform apply  # ⚠️ STOP MARKER - requires user confirmation
```

## Key Decisions

1. **Spec-First Development**: All code follows written specifications (specs/0X-*.md)
2. **LLM Models**: Restricted to deepseek:deepseek-chat (primary), openai:gpt-4o-mini (evals)
3. **Async Throughout**: FastAPI async design targeting <10s trip draft latency
4. **Pydantic Settings**: Environment-driven config, no hardcoded secrets
5. **Deterministic Tests**: Mocked LLM/DB, 80%+ coverage target
6. **LLM-Judged Evals**: Safety, factuality, budget gates in CI

## Common Tasks

### Add a new route
1. Create handler in `src/api/routes/`
2. Add to `src/api/routes/__init__.py`
3. Import and register in `src/api/main.py`
4. Test in `tests/unit/test_routes.py`

### Add evaluation criteria
1. Create judge in `src/evals/judges/`
2. Import in `src/evals/gate.py`
3. Call in `run_eval_gate()`
4. Test in `tests/unit/test_evals.py`

### Add LangGraph agent
1. Create async function in `src/agents/graph.py`
2. Add to graph with `graph.add_node()`
3. Add routing edges
4. Test state transitions

## CI/CD

GitHub Actions pipeline runs on every push/PR:
- Lint (ruff, black, pyright)
- Unit tests (80%+ coverage)
- Integration tests
- Docker build

⚠️ **STOP MARKER**: Terraform `apply` requires manual approval before infrastructure changes

## Support

For questions about Claude Code features, use `/help` or visit:
- Claude Code docs: https://claude.ai/code
- Claude API docs: https://docs.anthropic.com

Report issues: https://github.com/anthropics/claude-code/issues
