"""Database migration runner."""

import os
from pathlib import Path

from .db import db_pool


async def run_migrations():
    """Execute all database migrations in order."""
    migrations_dir = Path(__file__).parent / "migrations"

    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    for migration_file in migration_files:
        with open(migration_file, "r") as f:
            sql = f.read()

        # Execute migration
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
            await conn.commit()
