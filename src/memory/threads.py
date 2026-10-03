"""Thread and conversation history management."""

import json
from typing import Any, Optional, cast
from uuid import UUID, uuid4

from .db import db_pool


def _valid_uuid(value: str) -> bool:
    """True if value is a UUID string. Postgres raises on malformed ids in a UUID column."""
    try:
        UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _as_dict(value: Any) -> dict[str, Any]:
    """JSONB comes back from psycopg as a dict; a JSON string (older drivers, fakes) is parsed."""
    if not value:
        return {}
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    if isinstance(value, (str, bytes)):
        parsed: Any = json.loads(value)
        return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}
    return {}


async def create_thread(user_id: str, metadata: Optional[dict[str, Any]] = None) -> str:
    """Create new conversation thread."""
    thread_id = str(uuid4())

    query = """
    INSERT INTO threads (thread_id, user_id, metadata, created_at, updated_at)
    VALUES (%s, %s, %s, NOW(), NOW())
    """

    await db_pool.execute_insert(query, (thread_id, user_id, json.dumps(metadata or {})))

    return thread_id


async def get_thread(thread_id: str) -> Optional[dict[str, Any]]:
    """Retrieve thread metadata."""
    query = """
    SELECT thread_id, user_id, created_at, updated_at, metadata
    FROM threads WHERE thread_id = %s
    """

    if not _valid_uuid(thread_id):
        return None

    result = await db_pool.execute_one(query, (thread_id,))
    if result:
        return {
            "thread_id": str(result[0]),
            "user_id": result[1],
            "created_at": result[2].isoformat(),
            "updated_at": result[3].isoformat(),
            "metadata": _as_dict(result[4]),
        }
    return None


async def add_message(
    thread_id: str, role: str, content: str, metadata: Optional[dict[str, Any]] = None
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


async def get_history(thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve conversation history in chronological order."""
    query = """
    SELECT message_id, role, content, metadata, created_at FROM messages
    WHERE thread_id = %s
    ORDER BY created_at ASC
    LIMIT %s
    """

    if not _valid_uuid(thread_id):
        return []

    results = await db_pool.execute(query, (thread_id, limit))
    return [
        {
            "message_id": str(row[0]),
            "role": row[1],
            "content": row[2],
            "metadata": _as_dict(row[3]),
            "created_at": row[4].isoformat(),
        }
        for row in results
    ]


async def delete_thread(thread_id: str) -> None:
    """Delete thread and all associated data."""
    if not _valid_uuid(thread_id):
        return

    query = "DELETE FROM threads WHERE thread_id = %s"
    await db_pool.execute_insert(query, (thread_id,))


async def get_latest_plan(thread_id: str) -> Optional[dict[str, Any]]:
    """Return the most recent trip plan document stored for the thread, if any."""
    if not _valid_uuid(thread_id):
        return None

    query = """
    SELECT metadata -> 'plan' FROM messages
    WHERE thread_id = %s AND metadata ->> 'kind' = 'plan'
    ORDER BY created_at DESC
    LIMIT 1
    """
    row = await db_pool.execute_one(query, (thread_id,))
    if not row or not row[0]:
        return None
    return _as_dict(row[0]) or None


async def get_latest_approval(thread_id: str) -> Optional[dict[str, Any]]:
    """Return the latest approval decision ({approved, feedback}) recorded for the thread.

    Whether that decision still applies is up to the caller: the plan document says it itself
    (``plan["approval"]["approved"]`` stays None until the plan has been decided).
    """
    if not _valid_uuid(thread_id):
        return None

    query = """
    SELECT metadata FROM messages
    WHERE thread_id = %s AND role = 'human_approval'
    ORDER BY created_at DESC
    LIMIT 1
    """
    row = await db_pool.execute_one(query, (thread_id,))
    if not row:
        return None
    metadata = _as_dict(row[0])
    if "approved" not in metadata:
        return None
    return {"approved": bool(metadata["approved"]), "feedback": metadata.get("feedback") or ""}
