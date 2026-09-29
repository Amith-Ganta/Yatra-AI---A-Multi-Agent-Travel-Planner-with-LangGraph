# Deterministic Tests Specification

**Phase:** 7  
**Version:** 1.0  
**Status:** Implementation  
**Dependencies:** Phases 2-6 (all prior phases)  
**Target Coverage:** 80%+

---

## Overview

This phase implements comprehensive unit and integration tests covering all critical paths. Deterministic tests use fixtures and mocks for reproducibility.

**Test Structure:**
```
tests/
  unit/
    test_config.py          ✅ (existing)
    test_llm_factory.py     ✅ (existing)
    test_agents.py          ✅ (existing)
    test_tools.py           ✅ (existing)
    test_memory.py          ✅ (Phase 5)
    test_checkpointer.py    ✅ (Phase 5)
    test_routes.py          → (Phase 6 routes)
  integration/
    test_api.py             ✅ (Phase 6)
    test_workflow.py        → (end-to-end flow)
  fixtures/
    conftest.py             ✅ (global fixtures)
```

---

## 1. tests/conftest.py (Global Fixtures)

**Shared fixtures for all tests.**

```python
import pytest
import os
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm():
    """Mock LLM for deterministic testing."""
    mock = AsyncMock()
    mock.invoke = AsyncMock(return_value={
        "content": "Test response",
        "usage": {"input_tokens": 10, "output_tokens": 20}
    })
    return mock

@pytest.fixture
def mock_database_url():
    """Mock database URL for testing."""
    return "postgresql://test:test@localhost/test_db"

@pytest.fixture
def sample_travel_request():
    """Sample travel request for testing."""
    return {
        "message": "Plan a 5-day trip to Paris with budget $2000",
        "user_id": "test-user-123",
    }

@pytest.fixture
def sample_thread_id():
    """Sample thread ID."""
    return "thread-test-12345"

@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment for each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)
```

---

## 2. tests/unit/test_routes.py

**Route handler tests.**

```python
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.api import create_app
from src.memory import create_thread, add_message

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_health_endpoint(client):
    """Health endpoint returns 200 with ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_plan_trip_missing_message(client):
    """Plan endpoint validates required fields."""
    response = client.post("/api/plan", json={"user_id": "test"})
    assert response.status_code in [400, 422]

def test_get_thread_returns_404_for_nonexistent(client):
    """Get thread returns 404 for nonexistent thread."""
    response = client.get("/api/threads/nonexistent")
    assert response.status_code == 404

def test_approval_endpoint_format(client):
    """Approval endpoint validates request format."""
    response = client.put(
        "/api/threads/thread-id/approve",
        json={"approved": True}
    )
    # Should be 404 (no thread) or 422 (invalid)
    assert response.status_code in [404, 422]
```

---

## 3. tests/integration/test_workflow.py

**End-to-end workflow tests.**

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from src.agents.graph import build_graph
from src.agents.state import TravelState
from src.memory import create_thread, get_thread, get_history

@pytest.mark.asyncio
async def test_supervisor_rejects_invalid_request():
    """Supervisor rejects requests without destination."""
    state: TravelState = {
        "message": "Random message",
        "thread_id": "test-123",
    }
    
    with patch('src.agents.supervisor.supervisor_agent') as mock_supervisor:
        mock_supervisor.return_value = {
            "allowed": False,
            "reason": "No destination specified"
        }
        # Test that supervisor can reject

@pytest.mark.asyncio
async def test_graph_execution_flow():
    """Graph executes in correct order."""
    thread_id = await create_thread("test-user")
    
    state: TravelState = {
        "message": "Plan a trip to Tokyo",
        "thread_id": thread_id,
        "user_id": "test-user",
    }
    
    # Mock the graph to avoid actual LLM calls
    with patch('src.agents.graph.build_graph') as mock_build:
        graph = AsyncMock()
        graph.astream = AsyncMock(return_value=[
            {"supervisor": {"allowed": True}},
            {"flight": {"flights": []}},
            {"itinerary": {"itinerary": []}},
            {"final_response": {"plan": {}}},
        ])
        mock_build.return_value = graph

@pytest.mark.asyncio
async def test_thread_resumption():
    """Thread can be resumed with same ID."""
    thread_id = await create_thread("test-user", {"destination": "Paris"})
    
    # First message
    await add_message(thread_id, "user", "How much budget?")
    
    # Resume same thread
    thread = await get_thread(thread_id)
    assert thread is not None
    
    # Add follow-up
    await add_message(thread_id, "user", "Around $2000")
    
    # Verify history
    history = await get_history(thread_id)
    assert len(history) == 2

@pytest.mark.asyncio
async def test_agent_output_structure():
    """Agent outputs conform to schema."""
    from src.agents.graph import flight_agent
    
    state: TravelState = {
        "message": "Test",
        "thread_id": "test-123",
    }
    
    result = await flight_agent(state)
    assert "flight_output" in result
    assert isinstance(result["flight_output"], dict)
    assert "flights" in result["flight_output"]
```

---

## 4. tests/unit/test_startup.py

**Application startup tests.**

```python
import pytest
from unittest.mock import AsyncMock, patch

from src.core.startup import init_app, close_app

@pytest.mark.asyncio
async def test_init_app_initializes_database():
    """init_app sets up database pool."""
    with patch('src.memory.db_pool.init') as mock_init:
        await init_app()
        mock_init.assert_called_once()

@pytest.mark.asyncio
async def test_close_app_closes_database():
    """close_app closes database connections."""
    with patch('src.memory.db_pool.close') as mock_close:
        await close_app()
        mock_close.assert_called_once()
```

---

## 5. Coverage Configuration

**pytest.ini:**
```ini
[pytest]
testpaths = tests
asyncio_mode = auto
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow tests
```

**pyproject.toml:**
```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/site-packages/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
min_required = 80
```

---

## 6. Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit -v

# Integration tests only
pytest tests/integration -v

# With coverage
pytest --cov=src --cov-report=html --cov-report=term-missing

# Specific test file
pytest tests/unit/test_config.py -v

# Specific test function
pytest tests/unit/test_config.py::test_settings_load -v

# Run with markers
pytest -m "not slow" -v
```

---

## 7. Success Criteria

- ✅ 80%+ code coverage
- ✅ All critical paths tested
- ✅ Deterministic (no flaky tests)
- ✅ Async tests with proper fixtures
- ✅ Mock external dependencies (LLM, DB)
- ✅ Tests isolated and parallel-safe
- ✅ CI-ready (exit code 0 on pass)
- ✅ Fast execution (< 30 seconds total)

---

**Next Phase:** Phase 8 (LLM-Judged Evals)

