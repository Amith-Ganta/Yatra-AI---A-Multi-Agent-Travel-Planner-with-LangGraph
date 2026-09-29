# Yatra AI - Multi-Agent Travel Planner

Production-grade multi-agent travel planning system using LangGraph, powered by Claude/DeepSeek LLMs with PostgreSQL memory and LLM-based evaluation gates.

## Features

- **Multi-Agent Architecture**: Supervisor + 8 specialist agents (flight, hotel, weather, budget, itinerary, approval, final response)
- **LangGraph Checkpointing**: PostgreSQL-backed conversation history and thread resumption
- **Server-Sent Events (SSE)**: Real-time streaming of trip planning progress to clients
- **LLM-Judged Evals**: Safety, factuality, and budget validation gates in CI/CD
- **Async FastAPI**: Low-latency API targeting < 10s trip draft time
- **Deterministic Tests**: 80%+ code coverage with mocked LLM/DB dependencies
- **Docker + Terraform**: Production-ready containerization and AWS infrastructure

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Docker & Docker Compose (optional)
- API Keys: GROQ (or OpenAI), OpenAI, Tavily

### Local Development

```bash
# Clone repository
git clone https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph.git
cd Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph

# Create .env file
cp .env.example .env
# Edit .env with your API keys

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v --cov=src

# Start API server
python main.py
```

Server runs on `http://localhost:8000`

### Docker

```bash
# Build and start with docker-compose
docker-compose up --build

# API available at http://localhost:8000
# PostgreSQL at localhost:5432
```

## API Endpoints

### Health Check
```bash
GET /health          # Returns {"status": "ok"}
GET /ready           # Database readiness
```

### Trip Planning
```bash
POST /api/plan
Content-Type: application/json

{
  "message": "Plan a 5-day trip to Paris with $2000 budget",
  "user_id": "user-123",
  "thread_id": "optional-to-resume"
}

# Response: Server-Sent Events stream with progress updates
```

### Thread History
```bash
GET /api/threads/{thread_id}

# Response:
{
  "thread": {"thread_id": "...", "user_id": "...", "created_at": "..."},
  "history": [{"role": "user", "content": "...", "created_at": "..."}],
  "message_count": 5
}
```

### Human Approval
```bash
PUT /api/threads/{thread_id}/approve
Content-Type: application/json

{
  "approved": true,
  "feedback": "Looks great!"
}
```

## Architecture

```
Client Request
  ↓
FastAPI Endpoint
  ↓
Create/Resume Thread (PostgreSQL)
  ↓
LangGraph Supervisor
  ↓
4 Parallel Agents (Flight, Hotel, Weather, Budget)
  ↓
Itinerary Agent
  ↓
Evaluation Gate (Safety, Factuality, Budget)
  ↓
Human Approval (HITL)
  ↓
Final Response
  ↓
Save Checkpoint → PostgreSQL
  ↓
SSE Stream to Client
```

## Project Structure

```
.
├── specs/                      # Phase specifications
│   ├── 01-config.spec.md
│   ├── 02-agents.spec.md
│   ├── 03-tools-mcp.spec.md
│   └── ...
├── src/
│   ├── agents/                # LangGraph agents
│   │   ├── graph.py           # StateGraph + 8 agents
│   │   ├── supervisor.py      # Supervisor guardrails
│   │   └── routing.py         # Deterministic routing
│   ├── evals/                 # LLM-based judges
│   │   ├── judges/
│   │   │   ├── safety.py
│   │   │   ├── factuality.py
│   │   │   └── budget.py
│   │   └── gate.py            # Eval gate orchestrator
│   ├── api/                   # FastAPI application
│   │   ├── main.py            # App factory
│   │   └── routes/            # Endpoints
│   ├── memory/                # PostgreSQL integration
│   │   ├── db.py              # Connection pool
│   │   ├── checkpointer.py    # LangGraph checkpointer
│   │   ├── threads.py         # Thread management
│   │   └── migrations/        # Schema SQL
│   ├── tools/                 # MCP tool wrappers
│   └── core/                  # Config, logging, LLM factory
├── tests/
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── conftest.py            # Global fixtures
├── terraform/                 # AWS infrastructure
├── .github/
│   ├── workflows/ci.yml       # GitHub Actions CI
│   └── scripts/               # Utility scripts
├── Dockerfile                 # Container image
├── docker-compose.yml         # Local dev environment
└── main.py                    # Application entry point
```

## Development

### Running Tests
```bash
# All tests
pytest

# Unit only
pytest tests/unit/ -v

# Integration only
pytest tests/integration/ -v

# With coverage report
pytest --cov=src --cov-report=html

# Single test file
pytest tests/unit/test_agents.py -v
```

### Code Quality
```bash
# Format code
black src tests

# Lint
ruff check src tests

# Type check
pyright src
```

### Key Configuration (.env)

```
# LLM Models
LLM_RUNTIME_MODEL=deepseek:deepseek-chat
LLM_EVAL_MODEL=openai:gpt-4o-mini

# API Keys
GROQ_API_KEY=...
OPENAI_API_KEY=...
TAVILY_API_KEY=...

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/yatra_ai

# App
APP_ENV=development
APP_DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000

# Eval Thresholds
EVAL_SAFETY_THRESHOLD=0.95
EVAL_FACTUALITY_THRESHOLD=0.90
EVAL_BUDGET_THRESHOLD=0.95
```

## Deployment

### Docker Compose (Recommended for local/staging)
```bash
docker-compose up --build
```

### AWS + Terraform (Production)
```bash
cd terraform/
terraform init
terraform plan
terraform apply  # Requires manual confirmation
```

## Performance Targets

- **Trip Planning Latency**: < 10 seconds total
- **Agent Response Time**: < 3 seconds per agent
- **SSE Streaming**: Real-time progress updates
- **Test Coverage**: 80%+ of codebase
- **API Availability**: 99.9% uptime (with multi-AZ RDS)

## Evaluation Gates

All responses pass through LLM-based evaluation:

1. **Safety Judge**: Detects harmful content, risky recommendations
2. **Factuality Judge**: Validates accuracy of travel information
3. **Budget Judge**: Ensures cost stays within stated budget

Thresholds configurable via `.env`. Failures block CI/CD merges.

## CI/CD Pipeline

GitHub Actions runs automatically on push/PR:
1. **Lint**: ruff, black, pyright
2. **Test**: pytest with PostgreSQL service
3. **Coverage**: Uploaded to codecov
4. **Build**: Docker image build (no push)

All checks must pass before merging to main.

## Models Used

- **Runtime LLM**: DeepSeek (via GROQ API) - `deepseek:deepseek-chat`
- **Fallback LLM**: OpenAI - `openai:gpt-4o-mini`
- **Eval Judge**: OpenAI - `openai:gpt-4o-mini`

**Forbidden Models**: claude-*, gpt-4*, gpt-5.* (enforced at startup)

## Monitoring & Logging

- Structured JSON logging with trace IDs
- CloudWatch integration for production
- Eval gate metrics in CI output
- Database query logging (via psycopg)

## Known Limitations

1. Tool wrappers (Tavily, AviationStack, Open-Meteo) return placeholder data in Phase 4
2. Human approval agent auto-approves (HITL interrupts planned in Phase 6)
3. No AI cache optimization yet
4. Single-threaded for local dev

## Contributing

1. Create feature branch from `develop`: `git checkout -b phase-XX/feature-name`
2. Follow Conventional Commits format
3. Ensure 80%+ test coverage
4. Run CI checks locally before pushing
5. Create PR against `develop`

See [CLAUDE.md](CLAUDE.md) for Claude Code integration guidelines.

## License

MIT License - See LICENSE file

## Contact

- Repository: https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph
- Issues: https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph/issues

## Acknowledgments

Built with:
- [LangGraph](https://langchain-ai.github.io/langgraph/) - Agent orchestration
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Claude](https://www.anthropic.com/claude) - LLM backbone
- [PostgreSQL](https://www.postgresql.org/) - Memory layer
