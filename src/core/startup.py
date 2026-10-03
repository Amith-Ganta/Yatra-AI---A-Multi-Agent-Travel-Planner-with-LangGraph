"""Application startup and shutdown handlers."""

import asyncio
import sys
from urllib.parse import urlsplit

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


def _database_target(url: str) -> str:
    """Return ``host:port/name`` for log lines. The user, the password and the query never leave."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or "unknown-host"
        port = f":{parts.port}" if parts.port else ""
        return f"{host}{port}{parts.path}"
    except ValueError:
        return "unparseable DATABASE_URL"


def _connection_hint(url: str) -> str:
    """Explain a private hostname used from outside its network, the usual managed-host mistake."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    if host and "." not in host:
        return (
            " The host name has no domain, so it is a private (internal) address that only "
            "resolves inside the same provider region and workspace. If this service runs "
            "elsewhere, use the provider's external connection string instead."
        )
    return ""


async def _connect_database() -> None:
    """Open the connection pool, retrying while the database is still starting."""
    last_error: Exception | None = None
    target = _database_target(settings.database.url or "")
    for attempt in range(1, DB_CONNECT_ATTEMPTS + 1):
        try:
            await db_pool.init()
            return
        except Exception as e:
            last_error = e
            logger.warning(
                f"Database not reachable (attempt {attempt}/{DB_CONNECT_ATTEMPTS}) at {target}: "
                f"{type(e).__name__}",
                extra={"component": "startup"},
            )
            if attempt < DB_CONNECT_ATTEMPTS:
                await asyncio.sleep(DB_CONNECT_DELAY_SECONDS)
    raise RuntimeError(
        f"Could not connect to the database at {target} after {DB_CONNECT_ATTEMPTS} attempts."
        f"{_connection_hint(settings.database.url or '')}"
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
