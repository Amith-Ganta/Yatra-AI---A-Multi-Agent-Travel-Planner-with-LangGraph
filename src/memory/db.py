"""Async PostgreSQL connection pool and database operations."""

import json
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool


class DatabasePool:
    """Manages async PostgreSQL connection pool."""

    def __init__(self, database_url: str):
        self.pool: AsyncConnectionPool | None = None
        self.database_url = database_url

    async def init(self):
        """Initialize connection pool."""
        self.pool = AsyncConnectionPool(
            self.database_url,
            min_size=2,
            max_size=20,
        )
        await self.pool.open()

    async def close(self):
        """Close all connections."""
        if self.pool:
            await self.pool.close()

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from pool."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call init() first.")
        async with self.pool.connection() as conn:
            yield conn

    async def execute(self, query: str, params: tuple = ()) -> list[Any]:
        """Execute query and return results."""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchall()

    async def execute_one(self, query: str, params: tuple = ()) -> Any:
        """Execute query and return first result."""
        results = await self.execute(query, params)
        return results[0] if results else None

    async def execute_insert(self, query: str, params: tuple = ()) -> None:
        """Execute insert/update/delete query."""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
            await conn.commit()


db_pool = DatabasePool("")  # Will be initialized with config
