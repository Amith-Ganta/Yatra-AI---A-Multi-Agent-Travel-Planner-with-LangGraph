"""Tests for PostgreSQL checkpointer."""

import pytest
import json

from src.memory import PostgreSQLCheckpointer, db_pool, create_thread


@pytest.mark.asyncio
async def test_checkpointer_put():
    """Checkpointer stores state snapshot."""
    thread_id = await create_thread("user-checkpoint-1")
    checkpointer = PostgreSQLCheckpointer(db_pool)

    state = {
        "message": "Plan a trip",
        "selected_agents": ["flight", "hotel"],
        "thread_id": thread_id,
    }

    metadata = {"thread_id": thread_id, "step": 0}
    checkpoint_id = await checkpointer.put(state, metadata)

    assert checkpoint_id is not None


@pytest.mark.asyncio
async def test_checkpointer_get():
    """Checkpointer retrieves saved state."""
    thread_id = await create_thread("user-checkpoint-2")
    checkpointer = PostgreSQLCheckpointer(db_pool)

    state = {"message": "Plan a trip", "thread_id": thread_id}
    metadata = {"thread_id": thread_id, "step": 1}

    await checkpointer.put(state, metadata)
    retrieved = await checkpointer.get(thread_id, 1)

    assert retrieved is not None
    assert retrieved["message"] == "Plan a trip"


@pytest.mark.asyncio
async def test_checkpointer_get_nonexistent():
    """Get nonexistent checkpoint returns None."""
    checkpointer = PostgreSQLCheckpointer(db_pool)
    result = await checkpointer.get("nonexistent-thread", 999)

    assert result is None


@pytest.mark.asyncio
async def test_checkpointer_list():
    """List checkpoints for thread."""
    thread_id = await create_thread("user-checkpoint-3")
    checkpointer = PostgreSQLCheckpointer(db_pool)

    # Create multiple checkpoints
    for step in range(3):
        state = {"step": step, "thread_id": thread_id}
        metadata = {"thread_id": thread_id, "step": step}
        await checkpointer.put(state, metadata)

    checkpoints = await checkpointer.list_checkpoints(thread_id)

    assert len(checkpoints) == 3


@pytest.mark.asyncio
async def test_checkpointer_get_latest():
    """Get latest checkpoint for thread."""
    thread_id = await create_thread("user-checkpoint-4")
    checkpointer = PostgreSQLCheckpointer(db_pool)

    # Create multiple checkpoints
    for step in range(3):
        state = {"step": step, "thread_id": thread_id}
        metadata = {"thread_id": thread_id, "step": step}
        await checkpointer.put(state, metadata)

    latest = await checkpointer.get_latest(thread_id)

    assert latest is not None
    assert latest["step"] == 2


@pytest.mark.asyncio
async def test_checkpointer_update_existing():
    """Updating existing checkpoint step overwrites previous."""
    thread_id = await create_thread("user-checkpoint-5")
    checkpointer = PostgreSQLCheckpointer(db_pool)

    # First checkpoint
    state1 = {"data": "version1", "thread_id": thread_id}
    metadata = {"thread_id": thread_id, "step": 1}
    await checkpointer.put(state1, metadata)

    # Update same checkpoint
    state2 = {"data": "version2", "thread_id": thread_id}
    await checkpointer.put(state2, metadata)

    retrieved = await checkpointer.get(thread_id, 1)

    assert retrieved["data"] == "version2"
