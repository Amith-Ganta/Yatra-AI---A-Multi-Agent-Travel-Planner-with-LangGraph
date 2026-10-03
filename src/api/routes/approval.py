"""Human-in-the-loop approval endpoint.

When a run pauses at the approval step, the person answers here. The answer resumes the paused
graph on the same thread through ``Command(resume=...)`` and the new run is streamed as SSE, in
the same format as ``POST /api/plan``:

- approved: the graph finishes and the plan is final (status ``approved``)
- rejected with feedback: the itinerary is revised and the graph pauses again with a new draft,
  until the revision limit is reached (status ``revision_limit``, not approved)
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel

from src.agents.runtime import get_graph
from src.api.routes.planning import SSE_HEADERS
from src.api.streaming import graph_events, is_running
from src.core.telemetry import logger
from src.memory import add_message, get_thread

router = APIRouter(prefix="/api", tags=["approval"])


class ApprovalRequest(BaseModel):
    """The person's decision on a draft plan."""

    approved: bool
    feedback: Optional[str] = None


async def _has_pending_approval(thread_id: str) -> bool:
    """True when the thread's graph is paused at the approval step."""
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    snapshot = await get_graph().aget_state(config)
    return bool(snapshot.interrupts)


@router.put("/threads/{thread_id}/approve")
async def approve_trip(thread_id: str, request: ApprovalRequest):
    """Approve the draft plan, or reject it with feedback so the itinerary is revised."""
    feedback = (request.feedback or "").strip()
    try:
        if not await get_thread(thread_id):
            raise HTTPException(status_code=404, detail="Thread not found")

        # A rejection without a reason would only regenerate the same draft
        if not request.approved and not feedback:
            raise HTTPException(
                status_code=400,
                detail="Tell us what to change when you reject the plan.",
            )

        if is_running(thread_id) or not await _has_pending_approval(thread_id):
            raise HTTPException(
                status_code=409,
                detail="This trip has no plan waiting for approval.",
            )

        # Keep the decision in the thread history next to the plan it answers
        await add_message(
            thread_id,
            "human_approval",
            f"approved={request.approved}" + (f"; feedback={feedback}" if feedback else ""),
            {"kind": "approval", "approved": request.approved, "feedback": feedback},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Approval error", extra={"error": str(exc), "thread_id": thread_id})
        raise HTTPException(status_code=500, detail="Could not record the approval.")

    logger.info(
        "Trip approval received",
        extra={"thread_id": thread_id, "approved": request.approved},
    )
    decision: Command[Any] = Command(resume={"approved": request.approved, "feedback": feedback})
    return StreamingResponse(
        graph_events(decision, thread_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
