"""Yatra AI application entry point."""

import asyncio
import sys

# psycopg's async pool cannot run on Windows' default Proactor loop. Set the policy at import
# time so it also applies in the reloader's child process, which imports this module.
if sys.platform == "win32":
    # Deprecated from Python 3.14, but it is the only switch that works on 3.11 to 3.13
    asyncio.set_event_loop_policy(  # pyright: ignore[reportDeprecated]
        asyncio.WindowsSelectorEventLoopPolicy()  # pyright: ignore[reportDeprecated]
    )

from dotenv import load_dotenv  # noqa: E402

# Settings reads .env through pydantic, which does not touch os.environ. The tools and the MCP
# server subprocesses read TAVILY_API_KEY from the environment, so a local .env has to be loaded
# into it here. Real environment variables (Render, Docker) win over the file.
load_dotenv(override=False)

from src.api import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    import uvicorn

    from src.core.config import settings

    uvicorn.run(
        # An import string is required for reload to work
        "main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_level="info",
        # Newer uvicorn builds its own Proactor loop on Windows and ignores the policy above;
        # "none" makes it use the policy's selector loop instead.
        loop="none" if sys.platform == "win32" else "auto",
    )
