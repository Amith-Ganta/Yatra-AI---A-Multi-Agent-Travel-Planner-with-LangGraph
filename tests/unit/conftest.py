"""Pytest configuration for unit tests."""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from src.memory.db import DatabasePool


# In-memory simulated database for unit tests
_test_db = {
    "threads": {},  # thread_id -> thread data
    "messages": {},  # thread_id -> [messages]
    "checkpoints": {},  # (thread_id, step) -> state
}


# Mock connection and cursor (created once for all tests)
_mock_cursor = AsyncMock()
_mock_cursor.execute = AsyncMock()
_mock_cursor.fetchall = AsyncMock(return_value=[])

_mock_conn = AsyncMock()

@asynccontextmanager
async def _mock_cursor_cm():
    yield _mock_cursor

_mock_conn.cursor = _mock_cursor_cm
_mock_conn.commit = AsyncMock()

@asynccontextmanager
async def _mock_acquire():
    yield _mock_conn


async def _mock_execute_insert(query, params):
    """Simulate INSERT/UPDATE operations."""
    query_lower = query.lower()

    if "threads" in query_lower and "insert" in query_lower:
        # INSERT INTO threads (thread_id, user_id, metadata, created_at) VALUES (...)
        thread_id, user_id, metadata = params[0], params[1], params[2]
        _test_db["threads"][thread_id] = {"id": thread_id, "user_id": user_id, "metadata": metadata}
    elif "messages" in query_lower and "insert" in query_lower:
        # INSERT INTO messages (thread_id, role, content, metadata, created_at) VALUES (...)
        thread_id, role, content, metadata = params[0], params[1], params[2], params[3]
        if thread_id not in _test_db["messages"]:
            _test_db["messages"][thread_id] = []
        _test_db["messages"][thread_id].append({"thread_id": thread_id, "role": role, "content": content, "metadata": metadata})
    elif "checkpoints" in query_lower and "insert" in query_lower:
        # INSERT INTO checkpoints (checkpoint_id, thread_id, step, state, created_at) VALUES (...)
        checkpoint_id, thread_id, step, state = params[0], params[1], params[2], params[3]
        _test_db["checkpoints"][(thread_id, step)] = state


async def _mock_execute(query, params=()):
    """Simulate SELECT operations."""
    query_lower = query.lower()

    if "threads" in query_lower and "select" in query_lower:
        # SELECT * FROM threads WHERE thread_id = %s
        thread_id = params[0]
        if thread_id in _test_db["threads"]:
            thread = _test_db["threads"][thread_id]
            return [(thread["id"], thread["user_id"], thread["metadata"])]
        return []
    elif "messages" in query_lower and "select" in query_lower:
        # SELECT * FROM messages WHERE thread_id = %s
        thread_id = params[0]
        if thread_id in _test_db["messages"]:
            return [(msg["thread_id"], msg["role"], msg["content"], msg["metadata"]) for msg in _test_db["messages"][thread_id]]
        return []
    elif "checkpoints" in query_lower and "select" in query_lower:
        # SELECT state FROM checkpoints WHERE thread_id = %s AND step = %s
        thread_id, step = params[0], params[1]
        if (thread_id, step) in _test_db["checkpoints"]:
            return [(_test_db["checkpoints"][(thread_id, step)],)]
        return []

    return []


async def _mock_execute_one(query, params=()):
    """Simulate SELECT that returns one result."""
    results = await _mock_execute(query, params)
    return results[0] if results else None


@pytest.fixture(autouse=True)
def mock_db_pool(monkeypatch):
    """Mock database pool for all unit tests."""
    # Reset the test database before each test
    _test_db["threads"].clear()
    _test_db["messages"].clear()
    _test_db["checkpoints"].clear()

    # Patch the DatabasePool methods directly
    monkeypatch.setattr(DatabasePool, "acquire", _mock_acquire)
    monkeypatch.setattr(DatabasePool, "execute", AsyncMock(side_effect=_mock_execute))
    monkeypatch.setattr(DatabasePool, "execute_one", AsyncMock(side_effect=_mock_execute_one))
    monkeypatch.setattr(DatabasePool, "execute_insert", AsyncMock(side_effect=_mock_execute_insert))
    monkeypatch.setattr(DatabasePool, "init", AsyncMock())
    monkeypatch.setattr(DatabasePool, "close", AsyncMock())


@pytest.fixture
def client():
    """FastAPI test client."""
    from src.api.main import create_app

    app = create_app()
    from starlette.testclient import TestClient
    return TestClient(app)
