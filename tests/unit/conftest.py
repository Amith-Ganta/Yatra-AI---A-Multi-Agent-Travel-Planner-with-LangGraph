"""Pytest configuration for unit tests."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.runtime import close_graph, init_graph
from src.memory.db import DatabasePool

# In-memory simulated database for unit tests
_test_db = {
    "threads": {},  # thread_id -> thread data
    "messages": {},  # thread_id -> [messages]
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
async def _mock_acquire(*args, **kwargs):
    # Accepts (self, timeout=...) so it can replace the bound DatabasePool.acquire
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
        # INSERT INTO messages (message_id, thread_id, role, content, metadata, ...)
        if len(params) >= 5:
            message_id, thread_id, role, content, metadata = (
                params[0],
                params[1],
                params[2],
                params[3],
                params[4],
            )
            if thread_id not in _test_db["messages"]:
                _test_db["messages"][thread_id] = []
            _test_db["messages"][thread_id].append(
                {
                    "message_id": message_id,
                    "thread_id": thread_id,
                    "role": role,
                    "content": content,
                    "metadata": metadata,
                    "created_at": datetime.now(),
                }
            )
    elif "update threads" in query_lower:
        # UPDATE threads SET updated_at = NOW() WHERE thread_id = %s
        if len(params) >= 1 and params[0] in _test_db["threads"]:
            _test_db["threads"][params[0]]["updated_at"] = datetime.now()
    elif "delete from threads" in query_lower:
        # DELETE FROM threads WHERE thread_id = %s
        if len(params) >= 1 and params[0] in _test_db["threads"]:
            del _test_db["threads"][params[0]]
            if params[0] in _test_db["messages"]:
                del _test_db["messages"][params[0]]


async def _mock_execute(query, params=()):
    """Simulate SELECT operations."""
    query_lower = query.lower()

    if "from threads" in query_lower and "select" in query_lower:
        # SELECT thread_id, user_id, created_at, updated_at, metadata FROM threads ...
        if len(params) > 0:
            thread_id = params[0]
            if thread_id in _test_db["threads"]:
                t = _test_db["threads"][thread_id]
                return [(t["id"], t["user_id"], t["created_at"], t["updated_at"], t["metadata"])]
        return []
    elif "metadata -> 'plan'" in query_lower:
        # latest plan document: SELECT metadata -> 'plan' FROM messages WHERE kind = 'plan'
        plans = [
            json.loads(msg["metadata"])["plan"]
            for msg in _test_db["messages"].get(params[0], [])
            if json.loads(msg["metadata"]).get("kind") == "plan"
        ]
        return [(plans[-1],)] if plans else []
    elif "role = 'human_approval'" in query_lower:
        # latest decision: SELECT metadata FROM messages WHERE role = 'human_approval'
        decisions = [
            msg["metadata"]
            for msg in _test_db["messages"].get(params[0], [])
            if msg["role"] == "human_approval"
        ]
        return [(decisions[-1],)] if decisions else []
    elif "from messages" in query_lower and "select" in query_lower:
        # SELECT message_id, role, content, metadata, created_at FROM messages ...
        if len(params) > 0:
            thread_id = params[0]
            if thread_id in _test_db["messages"]:
                messages = _test_db["messages"][thread_id]
                limit = params[1] if len(params) > 1 else 50
                return [
                    (
                        msg["message_id"],
                        msg["role"],
                        msg["content"],
                        msg["metadata"],
                        msg["created_at"],
                    )
                    for msg in messages[:limit]
                ]
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

    # Patch the DatabasePool methods directly
    monkeypatch.setattr(DatabasePool, "acquire", _mock_acquire)
    monkeypatch.setattr(DatabasePool, "execute", AsyncMock(side_effect=_mock_execute))
    monkeypatch.setattr(DatabasePool, "execute_one", AsyncMock(side_effect=_mock_execute_one))
    monkeypatch.setattr(DatabasePool, "execute_insert", AsyncMock(side_effect=_mock_execute_insert))
    monkeypatch.setattr(DatabasePool, "init", AsyncMock())
    monkeypatch.setattr(DatabasePool, "close", AsyncMock())


@pytest.fixture(autouse=True)
def graph_runtime():
    """A fresh graph with an in-memory saver, so interrupt/resume works without Postgres."""
    init_graph(InMemorySaver())
    yield
    close_graph()


@pytest.fixture
def client():
    """FastAPI test client."""
    from src.api.main import create_app

    app = create_app()
    from starlette.testclient import TestClient

    return TestClient(app)
