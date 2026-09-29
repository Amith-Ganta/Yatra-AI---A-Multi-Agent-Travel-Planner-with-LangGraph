"""TravelState schema for LangGraph."""

from typing import Any, Optional
from typing_extensions import TypedDict
from datetime import datetime


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
