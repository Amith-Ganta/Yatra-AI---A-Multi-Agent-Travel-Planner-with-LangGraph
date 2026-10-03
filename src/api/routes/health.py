"""Health check endpoints."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.memory import db_pool
from src.tools.gateway import mcp_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

READINESS_PROBE_TIMEOUT_SECONDS = 3.0

FEATURES = [
    "supervisor_agent",
    "input_guardrail",
    "human_in_the_loop",
    "postgres_checkpointer",
    "mcp_tools",
]


@router.get("/health")
async def health_check():
    """Liveness check: the process is up."""
    return {"status": "ok", "service": "Yatra AI", "features": FEATURES}


@router.get("/ready")
async def readiness():
    """Readiness check: the database answers a query. Returns HTTP 503 when it does not."""
    if not db_pool.pool:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": "Database pool not initialized"},
        )

    try:
        async with db_pool.acquire(timeout=READINESS_PROBE_TIMEOUT_SECONDS) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
    except Exception:
        # Log the real error; do not leak connection details to the caller
        logger.exception("Readiness probe failed")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": "Database unavailable"},
        )

    # MCP state is informational: a server that is down only means its tool runs in-process
    return {"status": "ready", "mcp": mcp_status()}
