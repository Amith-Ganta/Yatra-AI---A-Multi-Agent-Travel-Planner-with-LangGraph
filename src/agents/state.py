"""TravelState schema for LangGraph."""

from datetime import datetime
from typing import Any, Optional

from typing_extensions import TypedDict


class TravelState(TypedDict, total=False):
    """Complete state for travel planning workflow."""

    # Input
    message: str
    thread_id: str

    # Supervisor output
    allowed: bool
    reason: str
    selected_agents: list[str]
    trip_constraints: dict[str, Any]

    # Agent outputs
    flight_output: Optional[dict[str, Any]]
    hotel_output: Optional[dict[str, Any]]
    weather_output: Optional[dict[str, Any]]
    budget_output: Optional[dict[str, Any]]
    itinerary_output: Optional[dict[str, Any]]

    # HITL
    human_approval: Optional[bool]
    feedback: Optional[str]
    revision_count: int

    # Final
    final_response: dict[str, Any]

    # Metadata
    created_at: datetime
    updated_at: datetime
    user_id: str
    model_used: str
    total_tokens: int
    cost_usd: float

    # Evaluation
    eval_scores: Optional[dict[str, float]]
    eval_passed: Optional[bool]


def new_request_state(message: str, thread_id: str, user_id: str) -> TravelState:
    """Input state for a new message on a thread.

    The checkpointer keeps a thread's state between runs, so a follow-up message would
    otherwise see the previous trip's outputs and approval. Every per-request key is reset here.
    """
    return {
        "message": message,
        "thread_id": thread_id,
        "user_id": user_id,
        "allowed": False,
        "reason": "",
        "selected_agents": [],
        "trip_constraints": {},
        "flight_output": None,
        "hotel_output": None,
        "weather_output": None,
        "budget_output": None,
        "itinerary_output": None,
        "human_approval": None,
        "feedback": "",
        "revision_count": 0,
        "final_response": {},
    }
