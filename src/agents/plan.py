"""Assemble the user-facing trip plan from the graph state.

The API reads the checkpointed state after every run (finished or paused at the approval step)
and turns it into one self-contained plan document. That document is what the frontend renders
and what is stored with the thread, so a plan can be reopened later without re-running the agents.

Plan statuses:

- ``rejected``           the supervisor did not accept the request (not travel, unsafe, unclear)
- ``awaiting_approval``  a draft is ready and the graph is paused for a person's decision
- ``approved``           a person approved the plan
- ``revision_limit``     the person kept asking for changes; this is the latest draft, not approved
"""

from typing import Any

from .trip import normalize_trip_constraints

REJECTED_FALLBACK = "This request could not be turned into a trip plan."
DRAFT_SUMMARY = "Draft plan ready for your review."


def _approval_info(state: dict[str, Any], *, awaiting: bool, max_revisions: int) -> dict[str, Any]:
    """Where the plan stands in the approve / revise loop."""
    itinerary: dict[str, Any] = state.get("itinerary_output") or {}
    final: dict[str, Any] = state.get("final_response") or {}
    return {
        "approved": None if awaiting else bool(final.get("approved")),
        "revision": int(state.get("revision_count") or 0),
        "max_revisions": max_revisions,
        # Set by the itinerary agent after a revision; None on the first draft
        "feedback_applied": itinerary.get("feedback_applied"),
        "revision_note": itinerary.get("revision_note"),
    }


def build_plan(
    state: dict[str, Any], *, awaiting_approval: bool = False, max_revisions: int = 3
) -> dict[str, Any]:
    """Build the plan document from the graph state.

    ``awaiting_approval`` is True when the run stopped at the approval interrupt, so the state
    holds a draft and no final response yet.
    """
    if not state.get("allowed", False):
        return {
            "status": "rejected",
            "reason": str(state.get("reason") or REJECTED_FALLBACK),
            "summary": None,
            "trip": None,
            "flights": None,
            "hotels": None,
            "weather": None,
            "budget": None,
            "itinerary": None,
            "approval": None,
        }

    trip = normalize_trip_constraints(state.get("trip_constraints"))
    final: dict[str, Any] = state.get("final_response") or {}
    approval = _approval_info(state, awaiting=awaiting_approval, max_revisions=max_revisions)

    if awaiting_approval:
        status = "awaiting_approval"
    elif approval["approved"]:
        status = "approved"
    else:
        status = "revision_limit"

    return {
        "status": status,
        "reason": str(state.get("reason") or ""),
        "summary": DRAFT_SUMMARY if awaiting_approval else final.get("summary"),
        "trip": trip.as_dict(),
        "flights": state.get("flight_output"),
        "hotels": state.get("hotel_output"),
        "weather": state.get("weather_output"),
        "budget": state.get("budget_output"),
        "itinerary": state.get("itinerary_output"),
        "approval": approval,
    }


def plan_message_text(plan: dict[str, Any]) -> str:
    """One-line text stored as the message content next to the plan document."""
    if plan.get("status") == "rejected":
        return plan.get("reason") or REJECTED_FALLBACK
    trip: dict[str, Any] = plan.get("trip") or {}
    destination = trip.get("destination") or "your destination"
    text = f"Trip plan for {destination}, {trip.get('start_date')} to {trip.get('end_date')}."
    if plan.get("status") == "awaiting_approval":
        return f"Draft: {text}"
    return text
