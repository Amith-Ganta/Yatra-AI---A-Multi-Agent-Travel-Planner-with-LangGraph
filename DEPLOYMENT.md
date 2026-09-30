# Yatra AI - Deployment Guide

## Project Status

✅ **All CI tiers passing:**
- Tier 1: Docker verification (build, start, health check)
- Tier 2: Unit tests (70/70 passing)
- Tier 3: Frontend build (Next.js 14)

## Quick Start - Local Deployment

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 20+

### Environment Setup

```bash
cp .env.example .env
```

Edit `.env` with required API keys:
```bash
OPENAI_API_KEY=sk-proj-...
DEEPSEEK_API_KEY=sk-...
TAVILY_API_KEY=...
```

### Deploy with Docker Compose

```bash
# Start all services (PostgreSQL + FastAPI + Next.js)
docker compose up -d

# Verify services are running
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

**Endpoints:**
- API: http://localhost:8000
- Health: http://localhost:8000/health
- Ready: http://localhost:8000/ready

### Services

| Service | Port | Status |
|---------|------|--------|
| PostgreSQL | 5432 | postgres:15-alpine |
| FastAPI | 8000 | Python 3.11 uvicorn |
| Frontend | 3000* | Next.js 14 (dev mode) |

*Frontend runs on port 3000 in dev mode; in production it's served via the FastAPI static files

## Production Deployment

### AWS EC2 Deployment

```bash
# 1. Launch Ubuntu 22.04 LTS instance
# 2. SSH into instance
ssh -i yatra-key.pem ubuntu@<EC2_IP>

# 3. Install dependencies
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git curl
sudo usermod -aG docker $USER
newgrp docker

# 4. Clone repository
git clone https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph.git
cd Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph

# 5. Configure environment
cat > .env << EOF
OPENAI_API_KEY=sk-proj-...
DEEPSEEK_API_KEY=sk-...
TAVILY_API_KEY=...
APP_ENV=production
APP_DEBUG=false
DATABASE_URL=postgresql://yatra:yatra_password@postgres:5432/yatra_ai
EOF

# 6. Deploy
docker compose up -d

# 7. Verify
curl http://localhost:8000/health
```

### Docker Hub Deployment

```bash
# 1. Build and push to Docker Hub
docker build -t yourusername/yatra-ai:latest .
docker push yourusername/yatra-ai:latest

# 2. Update docker-compose.yml
sed -i 's/build: \./image: yourusername\/yatra-ai:latest/' docker-compose.yml

# 3. Deploy on any Docker-enabled host
docker compose up -d
```

### Kubernetes Deployment

```bash
kubectl create namespace yatra-ai

# Update manifests in k8s/ directory with:
# - Image: yourusername/yatra-ai:latest
# - Secrets for API keys
# - PersistentVolume for PostgreSQL data

kubectl apply -f k8s/ -n yatra-ai
kubectl get all -n yatra-ai
```

## Health Checks & Monitoring

### Verify Deployment

```bash
# Check all services are healthy
docker compose ps

# View logs
docker compose logs api
docker compose logs postgres

# Health endpoint
curl -s http://localhost:8000/health | jq .

# Readiness endpoint (includes database check)
curl -s http://localhost:8000/ready | jq .
```

### Database Migrations

Migrations run automatically on app startup via lazy initialization:

```bash
# Manual migration if needed
docker compose exec api python -c "from src.memory.migrations import run_migrations; import asyncio; asyncio.run(run_migrations())"
```

## Scaling

### Horizontal Scaling (Multiple API Instances)

```bash
# Scale API service to 3 instances
docker compose up -d --scale api=3

# Use nginx reverse proxy (optional)
# Configure upstream in nginx.conf:
# upstream yatra_api {
#     server api:8000;
# }
```

### Database Connection Pooling

Already configured in `src/memory/db.py`:
- Pool size: 2-20 connections (configurable via settings)
- Connection timeout: 10s

## Troubleshooting

### App won't start
```bash
# Check logs
docker compose logs api

# Ensure .env has required keys
cat .env | grep -E "OPENAI|DEEPSEEK|TAVILY"

# Verify PostgreSQL is healthy
docker compose logs postgres
```

### Database connection fails
```bash
# Check PostgreSQL is running and ready
docker compose exec postgres pg_isready -U yatra

# Verify credentials in .env
docker compose down
docker volume rm <project>_postgres_data  # CAUTION: Deletes data
docker compose up -d
```

### Frontend not loading
```bash
# Check frontend build
docker compose exec api ls -la /app/frontend/out/

# View build errors
docker compose logs api | grep -i "error\|fail"
```

## API Endpoints

### Health & Status
- `GET /health` - Service health
- `GET /ready` - Readiness with database check

### Trip Planning
- `POST /api/plan` - Plan a trip
- `GET /api/thread/{threadId}` - Get trip details
- `POST /api/approve/{threadId}` - Approve/reject trip

## Performance

- Trip planning latency: < 10s (target)
- Database pool: 2-20 concurrent connections
- Frontend: Next.js static build (~100KB gzipped)

## Security

- Database credentials: Use `.env` (never commit)
- API keys: Set via environment variables
- HTTPS: Configure reverse proxy (nginx/caddy) for HTTPS
- CORS: Configured for `*` (update for production)

## Cleanup

```bash
# Stop services
docker compose down

# Remove data volumes (WARNING: Deletes database)
docker compose down -v

# Remove images
docker rmi yatra-ai:latest
docker image prune -a
```

## Support

For issues, check:
1. `.github/workflows/verify.yml` - CI pipeline (all tiers must pass)
2. `CLAUDE.md` - Project configuration and development
3. `docs/BLOCKED.md` - Known issues and debugging

---

**Status**: Ready for production deployment ✅
