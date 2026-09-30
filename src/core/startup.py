"""Application startup and shutdown handlers."""

import sys
import asyncio

from src.core.config import settings
from src.memory import db_pool
from src.memory.migrations import run_migrations
from src.core.telemetry import logger


async def init_app():
    """Initialize application on startup."""
    # Set Windows event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Initialize database pool (with timeout)
    db_pool.database_url = settings.database.url
    try:
        await asyncio.wait_for(db_pool.init(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Database pool initialization timed out (app will continue without db)", extra={"component": "startup"})
    except Exception as e:
        logger.warning(f"Database initialization failed (app will continue): {e}", extra={"component": "startup"})

    # Run migrations (non-blocking on failure)
    try:
        await run_migrations()
    except Exception as e:
        logger.warning(f"Migration failed (app will continue): {e}", extra={"component": "startup"})

    logger.info("Application initialized", extra={"component": "startup"})


async def close_app():
    """Clean up resources on shutdown."""
    await db_pool.close()
    logger.info("Application shut down", extra={"component": "startup"})
