"""Global test configuration and fixtures."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock

import pytest

# psycopg's async pool cannot run on the default Windows ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# Ensure test environment variables are set before any imports of config
os.environ.setdefault("OPENAI_API_KEY", "sk-proj-test-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-deepseek")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/test_yatra")
# Tests never launch the MCP subprocesses; the gateway falls back to the in-process tools.
os.environ.setdefault("MCP_ENABLED", "false")


@pytest.fixture
def mock_llm():
    """Mock LLM for deterministic testing."""
    mock = AsyncMock()
    mock.invoke = AsyncMock(
        return_value={
            "content": "Test response",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
    )
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
