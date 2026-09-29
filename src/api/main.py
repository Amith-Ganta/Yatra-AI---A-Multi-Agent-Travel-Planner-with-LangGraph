"""FastAPI application factory."""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.startup import init_app, close_app
from src.core.telemetry import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Starting Yatra AI application")
    await init_app()
    yield
    logger.info("Shutting down Yatra AI application")
    await close_app()


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    app = FastAPI(
        title="Yatra AI",
        description="Multi-agent travel planner with LangGraph",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    from src.api.routes import health_router, planning_router, approval_router

    app.include_router(health_router)
    app.include_router(planning_router)
    app.include_router(approval_router)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error("Unhandled exception", extra={"error": str(exc)})
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    return app
