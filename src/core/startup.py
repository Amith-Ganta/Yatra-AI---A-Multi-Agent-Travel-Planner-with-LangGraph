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

    # Initialize database pool
    db_pool.database_url = settings.database.url
    await db_pool.init()

    # Run migrations
    await run_migrations()

    logger.info("Application initialized", extra={"component": "startup"})


async def close_app():
    """Clean up resources on shutdown."""
    await db_pool.close()
    logger.info("Application shut down", extra={"component": "startup"})
