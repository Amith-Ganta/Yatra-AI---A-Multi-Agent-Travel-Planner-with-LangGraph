"""LangGraph SavepointsTrigger backed by PostgreSQL."""

import json
from uuid import uuid4
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointer

from .db import DatabasePool


class PostgreSQLCheckpointer(BaseCheckpointer):
    """LangGraph checkpointer backed by PostgreSQL."""

    def __init__(self, db_pool: DatabasePool):
        self.db = db_pool

    async def put(self, values: dict, metadata: dict) -> str:
        """Save checkpoint for thread."""
        thread_id = metadata.get("thread_id")
        step = metadata.get("step", 0)
        checkpoint_id = str(uuid4())

        query = """
        INSERT INTO checkpoints (checkpoint_id, thread_id, step, state, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (thread_id, step) DO UPDATE SET state = EXCLUDED.state
        """

        await self.db.execute_insert(query, (checkpoint_id, thread_id, step, json.dumps(values)))

        return checkpoint_id

    async def get(self, thread_id: str, step: int) -> Optional[dict]:
        """Retrieve checkpoint state."""
        query = "SELECT state FROM checkpoints WHERE thread_id = %s AND step = %s"

        result = await self.db.execute_one(query, (thread_id, step))

        if result:
            return json.loads(result[0])
        return None

    async def list_checkpoints(self, thread_id: str) -> list[dict]:
        """List all checkpoints for thread."""
        query = """
        SELECT checkpoint_id, step, created_at FROM checkpoints
        WHERE thread_id = %s
        ORDER BY step DESC
        """

        results = await self.db.execute(query, (thread_id,))
        return [
            {
                "checkpoint_id": row[0],
                "step": row[1],
                "created_at": row[2].isoformat(),
            }
            for row in results
        ]

    async def get_latest(self, thread_id: str) -> Optional[dict]:
        """Get most recent checkpoint for thread."""
        query = """
        SELECT state FROM checkpoints
        WHERE thread_id = %s
        ORDER BY step DESC
        LIMIT 1
        """

        result = await self.db.execute_one(query, (thread_id,))

        if result:
            return json.loads(result[0])
        return None
