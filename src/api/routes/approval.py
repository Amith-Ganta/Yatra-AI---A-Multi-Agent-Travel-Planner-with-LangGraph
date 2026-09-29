"""Human-in-the-loop approval endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.memory import get_thread, add_message
from src.core.telemetry import logger

router = APIRouter(prefix="/api", tags=["approval"])


class ApprovalRequest(BaseModel):
    """Human approval request."""

    approved: bool
    feedback: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Approval response."""

    thread_id: str
    approved: bool
    status: str


@router.put("/threads/{thread_id}/approve", response_model=ApprovalResponse)
async def approve_trip(thread_id: str, request: ApprovalRequest):
    """Submit human approval or rejection for trip plan."""
    try:
        thread = await get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Store approval in message history
        approval_message = f"approved={request.approved}"
        if request.feedback:
            approval_message += f"; feedback={request.feedback}"

        await add_message(thread_id, "human_approval", approval_message)

        logger.info(
            "Trip approval recorded",
            extra={"thread_id": thread_id, "approved": request.approved},
        )

        return ApprovalResponse(
            thread_id=thread_id,
            approved=request.approved,
            status="approval_recorded",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Approval error", extra={"error": str(e), "thread_id": thread_id})
        raise HTTPException(status_code=500, detail=str(e))
