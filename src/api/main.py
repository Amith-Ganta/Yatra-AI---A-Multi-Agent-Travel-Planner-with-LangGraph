"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.startup import close_app, init_app
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

    # CORS: only the configured frontend origins. The API sets no cookies and the frontend sends
    # no credentials, so they stay off (credentials plus a wildcard origin is the unsafe pair).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origin_list,
        allow_origin_regex=settings.app.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    # Routes
    from src.api.routes import approval_router, health_router, planning_router

    app.include_router(health_router)
    app.include_router(planning_router)
    app.include_router(approval_router)

    # Serve frontend static files if built
    frontend_build_path = Path(__file__).parent.parent.parent / "frontend" / ".next" / "static"
    frontend_public_path = Path(__file__).parent.parent.parent / "frontend" / "public"

    if frontend_build_path.exists():
        app.mount(
            "/_next/static", StaticFiles(directory=frontend_build_path), name="frontend_static"
        )

    if frontend_public_path.exists():
        app.mount("/public", StaticFiles(directory=frontend_public_path), name="frontend_public")

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception", extra={"error": str(exc)})
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    return app
