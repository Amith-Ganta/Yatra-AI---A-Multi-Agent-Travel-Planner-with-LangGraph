"""Thread helpers: UUID guard and JSONB decoding (F0 follow-ups found while testing on Postgres)."""

from datetime import datetime
from uuid import uuid4

import pytest

from src.memory import create_thread, db_pool, delete_thread, get_history, get_thread
from src.memory.threads import _as_dict, _valid_uuid


@pytest.mark.parametrize(
    "value, expected",
    [
        (str(uuid4()), True),
        ("nonexistent-thread-id", False),
        ("", False),
        ("12345", False),
        (None, False),
    ],
)
def test_valid_uuid(value, expected):
    assert _valid_uuid(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, {}),
        ("", {}),
        ({}, {}),
        ({"a": 1}, {"a": 1}),  # psycopg returns JSONB as dict
        ('{"a": 1}', {"a": 1}),  # JSON string
        (b'{"a": 1}', {"a": 1}),
        (42, {}),
    ],
)
def test_as_dict(value, expected):
    assert _as_dict(value) == expected


@pytest.mark.asyncio
async def test_malformed_thread_id_never_reaches_the_database(monkeypatch):
    """Postgres raises InvalidTextRepresentation for a bad UUID, which became an HTTP 500."""
    queries: list[str] = []

    async def spy(query, params=()):
        queries.append(query)
        return []

    monkeypatch.setattr(type(db_pool), "execute", lambda self, q, p=(): spy(q, p))
    monkeypatch.setattr(type(db_pool), "execute_one", lambda self, q, p=(): spy(q, p))
    monkeypatch.setattr(type(db_pool), "execute_insert", lambda self, q, p=(): spy(q, p))

    assert await get_thread("nonexistent-thread-id") is None
    assert await get_history("nonexistent-thread-id") == []
    await delete_thread("nonexistent-thread-id")

    assert queries == []


@pytest.mark.asyncio
async def test_driver_native_types_are_normalised(monkeypatch):
    """Postgres returns uuid.UUID and dict for UUID and JSONB columns; the API needs str/dict."""
    thread_uuid = uuid4()
    now = datetime(2026, 10, 1, 12, 0, 0)

    async def fake_execute_one(self, query, params=()):
        return (thread_uuid, "user-1", now, now, {"destination": "Rome"})

    monkeypatch.setattr(type(db_pool), "execute_one", fake_execute_one)

    thread = await get_thread(str(thread_uuid))

    assert thread["thread_id"] == str(thread_uuid)
    assert isinstance(thread["thread_id"], str)
    assert thread["metadata"] == {"destination": "Rome"}


@pytest.mark.asyncio
async def test_round_trip_still_works_with_the_fake_database():
    thread_id = await create_thread("u1", {"destination": "Paris"})
    thread = await get_thread(thread_id)
    assert thread["metadata"] == {"destination": "Paris"}
