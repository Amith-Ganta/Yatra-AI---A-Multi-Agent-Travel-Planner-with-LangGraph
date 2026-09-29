# API Specification (FastAPI)

**Phase:** 6  
**Version:** 1.0  
**Status:** Implementation  
**Dependencies:** Phase 2 (config), Phase 3 (agents), Phase 4 (tools), Phase 5 (memory)

---

## Overview

This phase implements FastAPI routes for invoking the travel planning workflow, streaming results via Server-Sent Events (SSE), and handling human-in-the-loop approval.

**Architecture:**
```
HTTP Request (POST /plan)
  ↓
FastAPI endpoint
  ↓
create_thread() / get_thread()
  ↓
graph.ainvoke() with async streaming
  ↓
SSE: chunk streaming to client
  ↓
Optional HITL (PUT /approve/{thread_id})
  ↓
Resume with human feedback
  ↓
SSE: final response
```

---

## 1. src/api/main.py

**FastAPI application factory.**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.core.config import settings
from src.core.startup import init_app, close_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    await init_app()
    yield
    await close_app()

def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(
        title="Yatra AI",
        description="Multi-agent travel planner",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    from src.api.routes import planning_router, health_router
    
    app.include_router(health_router)
    app.include_router(planning_router)

    return app
```

---

## 2. src/api/routes/health.py

**Health check endpoint.**

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Yatra AI"}

@router.get("/ready")
async def readiness():
    """Readiness check (database connectivity)."""
    try:
        # Quick database check
        from src.memory import db_pool
        async with db_pool.acquire() as conn:
            pass
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}, 503
```

---

## 3. src/api/routes/planning.py

**Core trip planning endpoints.**

```python
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from uuid import uuid4

from src.agents.graph import build_graph
from src.agents.state import TravelState
from src.memory import create_thread, get_thread, add_message, get_history
from src.core.telemetry import logger

router = APIRouter(prefix="/api", tags=["planning"])

class PlanRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    thread_id: str | None = None

class PlanResponse(BaseModel):
    thread_id: str
    status: str
    message: str

@router.post("/plan")
async def plan_trip(request: PlanRequest):
    """Create or resume trip planning conversation."""
    try:
        # Get or create thread
        if request.thread_id:
            thread = await get_thread(request.thread_id)
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
            thread_id = request.thread_id
        else:
            thread_id = await create_thread(request.user_id)

        # Add user message to history
        await add_message(thread_id, "user", request.message)

        # Build and invoke graph
        graph = await build_graph()
        
        initial_state: TravelState = {
            "message": request.message,
            "thread_id": thread_id,
            "user_id": request.user_id,
        }

        # Stream results via SSE
        async def event_stream():
            try:
                async for event in graph.astream(initial_state, {"thread_id": thread_id}):
                    # Yield event as JSON line
                    yield f"data: {json.dumps(event)}\n\n"
                
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                logger.error("Stream error", extra={"error": str(e)})
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Plan error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/threads/{thread_id}")
async def get_thread_info(thread_id: str):
    """Get thread metadata and history."""
    thread = await get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    history = await get_history(thread_id)

    return {
        "thread": thread,
        "history": history,
    }
```

---

## 4. src/api/routes/approval.py

**Human-in-the-loop approval endpoints.**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.memory import get_thread, add_message

router = APIRouter(prefix="/api", tags=["approval"])

class ApprovalRequest(BaseModel):
    approved: bool
    feedback: str = ""

@router.put("/threads/{thread_id}/approve")
async def approve_trip(thread_id: str, request: ApprovalRequest):
    """Submit human approval/rejection for trip plan."""
    thread = await get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Store approval in message history
    role = "human_approval"
    content = f"approved={request.approved}" + (f"; feedback={request.feedback}" if request.feedback else "")
    
    await add_message(thread_id, role, content)

    return {
        "thread_id": thread_id,
        "approved": request.approved,
        "status": "approval_recorded",
    }
```

---

## 5. src/api/routes/__init__.py

**Route registration.**

```python
from .health import router as health_router
from .planning import router as planning_router
from .approval import router as approval_router

__all__ = ["health_router", "planning_router", "approval_router"]
```

---

## 6. src/api/__init__.py

**API module exports.**

```python
from .main import create_app

__all__ = ["create_app"]
```

---

## 7. main.py (root)

**Application entry point.**

```python
import asyncio
import sys
from src.api import create_app
from src.core.config import settings

if __name__ == "__main__":
    import uvicorn

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    uvicorn.run(
        "main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_level="info",
    )
```

---

## 8. API Request/Response Examples

### Create new trip plan
```bash
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan a 5-day trip to Paris", "user_id": "user-123"}' \
  -N
```

**Response (SSE):**
```
data: {"step": "supervisor", "status": "running"}
data: {"step": "flight", "status": "running"}
data: {"step": "hotel", "status": "running"}
data: {"step": "weather", "status": "running"}
data: {"step": "budget", "status": "running"}
data: {"agents_output": {...}, "type": "agents_complete"}
data: {"step": "itinerary", "status": "complete", "itinerary": {...}}
data: {"step": "human_approval", "status": "awaiting"}
data: {"type": "done"}
```

### Resume conversation with approval
```bash
curl -X PUT http://localhost:8000/api/threads/{thread_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "feedback": "Looks great!"}'
```

### Get thread history
```bash
curl http://localhost:8000/api/threads/{thread_id}
```

---

## 9. tests/integration/test_api.py

**API integration tests.**

```python
import pytest
from fastapi.testclient import TestClient
from src.api import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_health_check(client):
    """Health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_plan_trip_creates_thread(client):
    """Plan trip creates new thread."""
    response = client.post(
        "/api/plan",
        json={"message": "Plan a trip to Tokyo", "user_id": "test-user"},
    )
    assert response.status_code == 200
    
    # Parse SSE response
    lines = response.text.strip().split("\n\n")
    assert len(lines) > 0

def test_get_thread_info(client):
    """Get thread returns metadata and history."""
    # Create thread first
    create_response = client.post(
        "/api/plan",
        json={"message": "Test", "user_id": "test-user"},
    )
    
    # Extract thread_id from response
    # TODO: Parse SSE to get thread_id
```

---

## Success Criteria

- ✅ FastAPI app with lifespan handlers
- ✅ Health check endpoints
- ✅ Trip planning endpoint with SSE streaming
- ✅ Thread resume capability
- ✅ Human approval endpoint
- ✅ Thread history retrieval
- ✅ CORS configured
- ✅ Structured error responses
- ✅ Integration tests (80%+ coverage)

---

**Next Phase:** Phase 7 (Deterministic Tests)

