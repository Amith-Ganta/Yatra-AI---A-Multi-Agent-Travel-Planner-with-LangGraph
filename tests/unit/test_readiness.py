"""Readiness probe (F3): /ready must return a real HTTP 503 when the database is unusable.

It used to return a (dict, 503) tuple, which FastAPI serialises as a JSON array with HTTP 200,
so orchestrators and `curl -f` treated an unready service as healthy.
"""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.memory import db_pool


@pytest.fixture
def client():
    return TestClient(create_app())


def test_not_ready_returns_http_503_and_a_json_object(client, monkeypatch):
    monkeypatch.setattr(db_pool, "pool", None)

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert isinstance(body, dict), "a (dict, 503) tuple would serialise as a list"
    assert body["status"] == "not_ready"


def test_ready_returns_200_when_the_probe_query_succeeds(client, monkeypatch):
    monkeypatch.setattr(db_pool, "pool", MagicMock())

    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    # No toolbox in unit tests, so MCP reports the in-process mode
    assert body["mcp"] == {"mode": "in-process"}


def test_probe_failure_returns_503_without_leaking_the_error(client, monkeypatch):
    monkeypatch.setattr(db_pool, "pool", MagicMock())

    @asynccontextmanager
    async def broken_acquire(*args, **kwargs):
        raise ConnectionError("password authentication failed for user secret_user")
        yield  # pragma: no cover

    monkeypatch.setattr(type(db_pool), "acquire", broken_acquire)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "secret_user" not in response.text
