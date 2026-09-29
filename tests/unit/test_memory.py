"""Tests for memory module (PostgreSQL and checkpointing)."""

import pytest
from datetime import datetime
from uuid import UUID

from src.memory import (
    create_thread,
    get_thread,
    add_message,
    get_history,
    delete_thread,
)


@pytest.mark.asyncio
async def test_create_thread():
    """Create new conversation thread."""
    thread_id = await create_thread("user-123")
    assert thread_id is not None
    assert isinstance(thread_id, str)
    assert len(thread_id) == 36  # UUID length


@pytest.mark.asyncio
async def test_create_thread_with_metadata():
    """Create thread with metadata."""
    metadata = {"destination": "Paris", "budget": 1000}
    thread_id = await create_thread("user-456", metadata)

    thread = await get_thread(thread_id)
    assert thread["metadata"] == metadata


@pytest.mark.asyncio
async def test_get_thread():
    """Retrieve thread metadata."""
    thread_id = await create_thread("user-789")
    thread = await get_thread(thread_id)

    assert thread is not None
    assert thread["user_id"] == "user-789"
    assert "created_at" in thread
    assert "updated_at" in thread


@pytest.mark.asyncio
async def test_get_nonexistent_thread():
    """Get nonexistent thread returns None."""
    thread = await get_thread("nonexistent-thread-id")
    assert thread is None


@pytest.mark.asyncio
async def test_add_message():
    """Add message to conversation."""
    thread_id = await create_thread("user-999")

    msg1_id = await add_message(thread_id, "user", "Plan a trip to Paris")
    msg2_id = await add_message(thread_id, "assistant", "I'll help you plan!")

    assert msg1_id is not None
    assert msg2_id is not None
    assert msg1_id != msg2_id


@pytest.mark.asyncio
async def test_get_history():
    """Retrieve conversation history."""
    thread_id = await create_thread("user-history-test")

    await add_message(thread_id, "user", "First message")
    await add_message(thread_id, "assistant", "Response")
    await add_message(thread_id, "user", "Follow-up")

    history = await get_history(thread_id)

    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "First message"
    assert history[1]["role"] == "assistant"
    assert history[2]["role"] == "user"
    assert history[2]["content"] == "Follow-up"


@pytest.mark.asyncio
async def test_get_history_empty():
    """Get history for empty thread."""
    thread_id = await create_thread("user-empty")
    history = await get_history(thread_id)

    assert history == []


@pytest.mark.asyncio
async def test_get_history_limit():
    """History respects limit parameter."""
    thread_id = await create_thread("user-limit-test")

    for i in range(10):
        await add_message(thread_id, "user", f"Message {i}")

    history = await get_history(thread_id, limit=5)
    assert len(history) == 5


@pytest.mark.asyncio
async def test_add_message_with_metadata():
    """Add message with metadata."""
    thread_id = await create_thread("user-metadata")
    metadata = {"source": "api", "version": "1.0"}

    msg_id = await add_message(thread_id, "user", "Test", metadata)

    history = await get_history(thread_id)
    assert len(history) == 1
    assert history[0]["metadata"] == metadata


@pytest.mark.asyncio
async def test_thread_update_time():
    """Thread updated_at changes when message added."""
    thread_id = await create_thread("user-update-time")
    thread1 = await get_thread(thread_id)

    import asyncio

    await asyncio.sleep(0.1)
    await add_message(thread_id, "user", "Message")

    thread2 = await get_thread(thread_id)
    assert thread2["updated_at"] >= thread1["updated_at"]


@pytest.mark.asyncio
async def test_delete_thread():
    """Delete thread removes all data."""
    thread_id = await create_thread("user-delete")
    await add_message(thread_id, "user", "Message")

    await delete_thread(thread_id)

    thread = await get_thread(thread_id)
    assert thread is None

    history = await get_history(thread_id)
    assert history == []
