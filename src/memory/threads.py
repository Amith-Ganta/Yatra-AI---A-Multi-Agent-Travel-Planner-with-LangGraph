"""Thread and conversation history management."""

import json
from uuid import uuid4
from typing import Optional

from .db import db_pool


async def create_thread(user_id: str, metadata: Optional[dict] = None) -> str:
    """Create new conversation thread."""
    thread_id = str(uuid4())

    query = """
    INSERT INTO threads (thread_id, user_id, metadata, created_at, updated_at)
    VALUES (%s, %s, %s, NOW(), NOW())
    """

    await db_pool.execute_insert(query, (thread_id, user_id, json.dumps(metadata or {})))

    return thread_id


async def get_thread(thread_id: str) -> Optional[dict]:
    """Retrieve thread metadata."""
    query = """
    SELECT thread_id, user_id, created_at, updated_at, metadata
    FROM threads WHERE thread_id = %s
    """

    result = await db_pool.execute_one(query, (thread_id,))
    if result:
        return {
            "thread_id": result[0],
            "user_id": result[1],
            "created_at": result[2].isoformat(),
            "updated_at": result[3].isoformat(),
            "metadata": json.loads(result[4]) if result[4] else {},
        }
    return None


async def add_message(
    thread_id: str, role: str, content: str, metadata: Optional[dict] = None
) -> str:
    """Add message to conversation history."""
    message_id = str(uuid4())

    query = """
    INSERT INTO messages (message_id, thread_id, role, content, metadata, created_at)
    VALUES (%s, %s, %s, %s, %s, NOW())
    """

    await db_pool.execute_insert(
        query, (message_id, thread_id, role, content, json.dumps(metadata or {}))
    )

    # Update thread's updated_at timestamp
    update_query = "UPDATE threads SET updated_at = NOW() WHERE thread_id = %s"
    await db_pool.execute_insert(update_query, (thread_id,))

    return message_id


async def get_history(thread_id: str, limit: int = 50) -> list[dict]:
    """Retrieve conversation history in chronological order."""
    query = """
    SELECT message_id, role, content, metadata, created_at FROM messages
    WHERE thread_id = %s
    ORDER BY created_at ASC
    LIMIT %s
    """

    results = await db_pool.execute(query, (thread_id, limit))
    return [
        {
            "message_id": row[0],
            "role": row[1],
            "content": row[2],
            "metadata": json.loads(row[3]) if row[3] else {},
            "created_at": row[4].isoformat(),
        }
        for row in results
    ]


async def delete_thread(thread_id: str) -> None:
    """Delete thread and all associated data."""
    query = "DELETE FROM threads WHERE thread_id = %s"
    await db_pool.execute_insert(query, (thread_id,))
