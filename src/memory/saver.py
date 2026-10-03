"""LangGraph checkpoint storage on PostgreSQL.

``AsyncPostgresSaver`` is what lets the approval step survive a pause: the graph state is saved
at every step, so a run stopped at ``interrupt()`` can be resumed by a later request, on any
worker, even after a restart.

The saver needs connections with ``autocommit=True``, ``prepare_threshold=0`` and dict rows. The
repository's own pool uses psycopg's defaults (explicit commits), so the saver gets a pool of its
own instead of sharing one with different settings.
"""

from typing import Any, Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class CheckpointStore:
    """Owns the saver's connection pool and the saver itself."""

    def __init__(self) -> None:
        self._pool: Optional[AsyncConnectionPool[Any]] = None
        self._saver: Optional[AsyncPostgresSaver] = None

    @property
    def saver(self) -> AsyncPostgresSaver:
        """The saver to compile the graph with; only valid after ``init``."""
        if self._saver is None:
            raise RuntimeError("Checkpoint store not initialized. Call init() first.")
        return self._saver

    async def init(self, database_url: str, timeout: float = 15.0) -> None:
        """Open the pool and create the saver's tables.

        Run it after the SQL migrations: migration 002 removes the legacy ``checkpoints`` table
        that would otherwise collide with the saver's own table of the same name.
        """
        pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
            database_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        try:
            await pool.open(wait=True, timeout=timeout)
            saver = AsyncPostgresSaver(pool)  # pyright: ignore[reportArgumentType]
            await saver.setup()
        except Exception:
            await pool.close()
            raise
        self._pool = pool
        self._saver = saver

    async def close(self) -> None:
        """Close the pool; safe to call twice."""
        if self._pool is not None:
            await self._pool.close()
        self._pool = None
        self._saver = None


checkpoint_store = CheckpointStore()
