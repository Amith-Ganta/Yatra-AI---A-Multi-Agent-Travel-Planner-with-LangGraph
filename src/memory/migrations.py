"""Database migration runner."""

from pathlib import Path
from typing import LiteralString, cast

from .db import db_pool


async def run_migrations() -> None:
    """Execute all database migrations in order."""
    migrations_dir = Path(__file__).parent / "migrations"

    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    for migration_file in migration_files:
        # The files ship with the repository and take no user input, so the text is trusted.
        sql = cast(LiteralString, migration_file.read_text(encoding="utf-8"))

        # Execute migration
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
            await conn.commit()
