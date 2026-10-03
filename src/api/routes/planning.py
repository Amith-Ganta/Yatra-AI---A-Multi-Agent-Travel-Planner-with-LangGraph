"""Trip planning endpoints.

POST /api/plan streams server-sent events (the event types are documented in
``src.api.streaming``). A run either finishes with a plan, or pauses with an
``approval_required`` event until the person answers through the approve endpoint.

Sending a new message on a thread that is paused for approval starts a fresh request on that
thread: the pending approval is dropped and the new message is planned from scratch.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agents.state import new_request_state
from src.api.streaming import graph_events
from src.core.telemetry import logger
from src.memory import (
    add_message,
    create_thread,
    get_history,
    get_latest_approval,
    get_latest_plan,
    get_thread,
)

router = APIRouter(prefix="/api", tags=["planning"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class PlanRequest(BaseModel):
    """Trip planning request."""

    message: str = Field(min_length=1, max_length=4000)
    user_id: str = "anonymous"
    thread_id: Optional[str] = None


@router.post("/plan")
async def plan_trip(request: PlanRequest):
    """Create or continue a trip planning conversation, streamed as SSE."""
    try:
        if request.thread_id:
            if not await get_thread(request.thread_id):
                raise HTTPException(status_code=404, detail="Thread not found")
            thread_id = request.thread_id
        else:
            thread_id = await create_thread(request.user_id)

        await add_message(thread_id, "user", request.message)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Plan error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Could not start trip planning.")

    # Every key is reset: the checkpointer keeps state per thread, so a second message must not
    # inherit the previous plan, approval or revision count.
    initial_state = new_request_state(request.message, thread_id, request.user_id)
    return StreamingResponse(
        graph_events(initial_state, thread_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/threads/{thread_id}", response_model=dict[str, Any])
async def get_thread_info(thread_id: str) -> dict[str, Any]:
    """Thread metadata, conversation history, the latest plan and the latest approval."""
    try:
        thread = await get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        history = await get_history(thread_id)
        plan = await get_latest_plan(thread_id)
        # A decision belongs to the plan it answered: a new or revised draft is still open
        approval_state: dict[str, Any] = (plan or {}).get("approval") or {}
        decided = approval_state.get("approved") is not None

        return {
            "thread": thread,
            "history": history,
            "message_count": len(history),
            "plan": plan,
            "approval": await get_latest_approval(thread_id) if decided else None,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Get thread error", extra={"error": str(exc), "thread_id": thread_id})
        raise HTTPException(status_code=500, detail="Could not load the thread.")
