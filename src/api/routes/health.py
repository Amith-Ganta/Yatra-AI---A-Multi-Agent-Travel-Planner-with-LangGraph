"""Health check endpoints."""

from fastapi import APIRouter

from src.memory import db_pool

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Yatra AI"}


@router.get("/ready")
async def readiness():
    """Readiness check (database connectivity)."""
    try:
        if not db_pool.pool:
            return {"status": "not_ready", "error": "Database pool not initialized"}, 503

        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")

        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}, 503
