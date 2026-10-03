"""Application startup and shutdown handlers."""

import asyncio
import sys

from src.agents.runtime import close_graph, init_graph
from src.core.config import settings
from src.core.telemetry import logger
from src.memory import checkpoint_store, db_pool
from src.memory.migrations import run_migrations
from src.tools.gateway import mcp_status, start_mcp, stop_mcp

# Postgres can be a few seconds behind the API container (docker compose, managed hosts),
# so retry for a short while, then fail fast and let the orchestrator restart the process.
DB_CONNECT_ATTEMPTS = 10
DB_CONNECT_DELAY_SECONDS = 2.0


async def _connect_database() -> None:
    """Open the connection pool, retrying while the database is still starting."""
    last_error: Exception | None = None
    for attempt in range(1, DB_CONNECT_ATTEMPTS + 1):
        try:
            await db_pool.init()
            return
        except Exception as e:
            last_error = e
            logger.warning(
                f"Database not reachable (attempt {attempt}/{DB_CONNECT_ATTEMPTS}): "
                f"{type(e).__name__}",
                extra={"component": "startup"},
            )
            if attempt < DB_CONNECT_ATTEMPTS:
                await asyncio.sleep(DB_CONNECT_DELAY_SECONDS)
    raise RuntimeError(
        f"Could not connect to the database after {DB_CONNECT_ATTEMPTS} attempts"
    ) from last_error


async def init_app() -> None:
    """Initialize application on startup: open the DB pool and apply migrations."""
    # psycopg's async pool needs the selector loop on Windows
    if sys.platform == "win32":
        # Deprecated in Python 3.14 but still the only switch that works on 3.11 to 3.13
        asyncio.set_event_loop_policy(  # pyright: ignore[reportDeprecated]
            asyncio.WindowsSelectorEventLoopPolicy()  # pyright: ignore[reportDeprecated]
        )

    if not settings.database.url:
        raise RuntimeError("DATABASE_URL is not set; the API cannot start without a database")
    db_pool.database_url = settings.database.url

    await _connect_database()
    await run_migrations()

    # The saver creates its own tables, so it must come after the migrations (see 002).
    await checkpoint_store.init(settings.database.url)
    init_graph(checkpoint_store.saver)

    # Never raises: a server that cannot start is skipped and its tools fall back in-process.
    await start_mcp()

    logger.info(
        "Application initialized",
        extra={"component": "startup", "mcp": mcp_status()},
    )


async def close_app() -> None:
    """Clean up resources on shutdown, in the reverse order of startup."""
    await stop_mcp()
    close_graph()
    await checkpoint_store.close()
    await db_pool.close()
    logger.info("Application shut down", extra={"component": "startup"})
