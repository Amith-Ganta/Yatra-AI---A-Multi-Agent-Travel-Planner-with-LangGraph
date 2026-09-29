"""Trip planning endpoints."""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from src.agents.graph import build_graph
from src.agents.state import TravelState
from src.memory import create_thread, get_thread, add_message, get_history
from src.core.telemetry import logger

router = APIRouter(prefix="/api", tags=["planning"])


class PlanRequest(BaseModel):
    """Trip planning request."""

    message: str
    user_id: str = "anonymous"
    thread_id: Optional[str] = None


class ThreadResponse(BaseModel):
    """Thread information response."""

    thread_id: str
    user_id: str
    created_at: str
    updated_at: str
    metadata: dict


class MessageResponse(BaseModel):
    """Message in conversation history."""

    message_id: str
    role: str
    content: str
    created_at: str
    metadata: dict


@router.post("/plan")
async def plan_trip(request: PlanRequest):
    """Create or resume trip planning conversation with SSE streaming."""
    try:
        # Get or create thread
        if request.thread_id:
            thread = await get_thread(request.thread_id)
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
            thread_id = request.thread_id
        else:
            thread_id = await create_thread(request.user_id)

        # Add user message to history
        await add_message(thread_id, "user", request.message)

        # Build graph
        graph = await build_graph()

        # Initial state
        initial_state: TravelState = {
            "message": request.message,
            "thread_id": thread_id,
            "user_id": request.user_id,
        }

        # Stream results via SSE
        async def event_stream():
            try:
                async for event in graph.astream(
                    initial_state, {"thread_id": thread_id, "configurable": {"thread_id": thread_id}}
                ):
                    yield f"data: {json.dumps(event, default=str)}\n\n"

                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                logger.error("Stream error", extra={"error": str(e), "thread_id": thread_id})
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Plan error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/{thread_id}", response_model=dict)
async def get_thread_info(thread_id: str):
    """Get thread metadata and conversation history."""
    try:
        thread = await get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        history = await get_history(thread_id)

        return {
            "thread": thread,
            "history": history,
            "message_count": len(history),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get thread error", extra={"error": str(e), "thread_id": thread_id})
        raise HTTPException(status_code=500, detail=str(e))
