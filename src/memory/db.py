"""Async PostgreSQL connection pool and database operations."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, LiteralString

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool


class DatabasePool:
    """Manages async PostgreSQL connection pool."""

    def __init__(self, database_url: str):
        self.pool: AsyncConnectionPool[Any] | None = None
        self.database_url = database_url

    async def init(self, timeout: float = 15.0) -> None:
        """Open the pool and wait until it holds working connections.

        Raises if the database cannot be reached within `timeout` seconds, so a bad
        DATABASE_URL fails at startup instead of on the first request.
        """
        pool = AsyncConnectionPool(
            self.database_url,
            min_size=2,
            max_size=20,
            open=False,
        )
        try:
            await pool.open(wait=True, timeout=timeout)
        except Exception:
            await pool.close()
            raise
        self.pool = pool

    async def close(self) -> None:
        """Close all connections."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def acquire(
        self, timeout: float | None = None
    ) -> AsyncGenerator[AsyncConnection[Any], None]:
        """Acquire a connection from pool (optionally with a shorter wait than the default)."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call init() first.")
        async with self.pool.connection(timeout=timeout) as conn:
            yield conn

    async def execute(
        self, query: LiteralString, params: tuple[Any, ...] = ()
    ) -> list[tuple[Any, ...]]:
        """Execute query and return results."""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchall()

    async def execute_one(
        self, query: LiteralString, params: tuple[Any, ...] = ()
    ) -> tuple[Any, ...] | None:
        """Execute query and return first result."""
        results = await self.execute(query, params)
        return results[0] if results else None

    async def execute_insert(self, query: LiteralString, params: tuple[Any, ...] = ()) -> None:
        """Execute insert/update/delete query."""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
            await conn.commit()


db_pool = DatabasePool("")  # Will be initialized with config
