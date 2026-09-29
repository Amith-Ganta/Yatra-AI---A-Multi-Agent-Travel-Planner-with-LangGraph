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
    from datetime import datetime
    query_lower = query.lower()

    if "insert into threads" in query_lower:
        # INSERT INTO threads (thread_id, user_id, metadata, created_at, updated_at) VALUES (...)
        if len(params) >= 3:
            thread_id, user_id, metadata = params[0], params[1], params[2]
            _test_db["threads"][thread_id] = {
                "id": thread_id,
                "user_id": user_id,
                "metadata": metadata,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
    elif "insert into messages" in query_lower:
        # INSERT INTO messages (message_id, thread_id, role, content, metadata, created_at) VALUES (...)
        if len(params) >= 5:
            message_id, thread_id, role, content, metadata = params[0], params[1], params[2], params[3], params[4]
            if thread_id not in _test_db["messages"]:
                _test_db["messages"][thread_id] = []
            _test_db["messages"][thread_id].append({
                "message_id": message_id,
                "thread_id": thread_id,
                "role": role,
                "content": content,
                "metadata": metadata,
                "created_at": datetime.now(),
            })
    elif "insert into checkpoints" in query_lower:
        # INSERT INTO checkpoints (checkpoint_id, thread_id, step, state, created_at) VALUES (...)
        if len(params) >= 4:
            checkpoint_id, thread_id, step, state = params[0], params[1], params[2], params[3]
            _test_db["checkpoints"][(thread_id, step)] = state
    elif "update threads" in query_lower:
        # UPDATE threads SET updated_at = NOW() WHERE thread_id = %s
        if len(params) >= 1 and params[0] in _test_db["threads"]:
            _test_db["threads"][params[0]]["updated_at"] = datetime.now()


async def _mock_execute(query, params=()):
    """Simulate SELECT operations."""
    from datetime import datetime
    query_lower = query.lower()

    if "from threads" in query_lower and "select" in query_lower:
        # SELECT thread_id, user_id, created_at, updated_at, metadata FROM threads WHERE thread_id = %s
        if len(params) > 0:
            thread_id = params[0]
            if thread_id in _test_db["threads"]:
                t = _test_db["threads"][thread_id]
                return [(t["id"], t["user_id"], t["created_at"], t["updated_at"], t["metadata"])]
        return []
    elif "from messages" in query_lower and "select" in query_lower:
        # SELECT message_id, role, content, metadata, created_at FROM messages WHERE thread_id = %s ORDER BY created_at ASC LIMIT %s
        if len(params) > 0:
            thread_id = params[0]
            if thread_id in _test_db["messages"]:
                messages = _test_db["messages"][thread_id]
                limit = params[1] if len(params) > 1 else 50
                return [(msg["message_id"], msg["role"], msg["content"], msg["metadata"], msg["created_at"]) for msg in messages[:limit]]
        return []
    elif "from checkpoints" in query_lower and "select" in query_lower:
        # SELECT state FROM checkpoints WHERE thread_id = %s AND step = %s
        if len(params) >= 2:
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
