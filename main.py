"""Yatra AI application entry point."""

import sys
import asyncio

from src.api import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    # Windows event loop policy
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    from src.core.config import settings

    uvicorn.run(
        app,
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_level="info",
    )
