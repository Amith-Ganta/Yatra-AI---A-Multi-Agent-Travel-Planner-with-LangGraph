"""Deterministic routing logic for agents.

Execution shape (each node runs at most once per request):

    supervisor -> [flight | hotel | weather]  (parallel research wave)
               -> budget                      (only if selected; needs flight and hotel output)
               -> itinerary -> human_approval -> final_response

human_approval pauses the graph (a LangGraph interrupt) until the user answers. A rejection
loops through ``revise`` back to itinerary, at most ``settings.mcp.max_revisions`` times.
"""

from typing import Any

from src.core.config import settings

# Workers that research independently of each other, so they can run in parallel.
RESEARCH_AGENTS = ["flight", "hotel", "weather"]

# Logical order of the whole pipeline (budget needs the research output, itinerary needs all).
AGENT_ORDER = [*RESEARCH_AGENTS, "budget", "itinerary"]


def should_run_agent(agent_name: str, selected_agents: list[str]) -> bool:
    """Determine if an agent should run."""
    if agent_name == "itinerary":
        return True  # Itinerary always runs
    if agent_name in ["human_approval", "final_response"]:
        return True  # Approval and final always run
    return agent_name in selected_agents


def get_agent_sequence(selected_agents: list[str]) -> list[str]:
    """Return agents in execution order, skipping unselected."""
    return [a for a in AGENT_ORDER if should_run_agent(a, selected_agents)]


def get_research_agents(selected_agents: list[str]) -> list[str]:
    """Return the selected research workers, in a stable order."""
    return [a for a in RESEARCH_AGENTS if a in selected_agents]


def route_from_supervisor(state: dict[str, Any]) -> list[str] | str:
    """Route from supervisor based on guardrail decision.

    Returns only the research workers for the parallel wave. Budget and itinerary are
    reached through route_from_workers, so no node is scheduled twice.
    """
    if not state.get("allowed", False):
        return "final_response"  # Skip to final with rejection

    selected: list[str] = state.get("selected_agents") or []

    research = get_research_agents(selected)
    if research:
        return research

    # No research workers selected: budget may still run, otherwise go straight to itinerary
    if "budget" in selected:
        return "budget"
    return "itinerary"


def route_from_workers(state: dict[str, Any]) -> str:
    """Route from a research worker to budget (if selected) or itinerary.

    Every worker in the wave returns the same target, and LangGraph merges identical
    targets in one superstep, so the next node runs once after the whole wave completes.
    """
    selected: list[str] = state.get("selected_agents") or []
    return "budget" if "budget" in selected else "itinerary"


def route_from_approval(state: dict[str, Any]) -> str:
    """Route from the human decision.

    Approved goes to the final response. A rejection goes to ``revise`` until the revision
    budget is used up; after that the latest draft is accepted as is, so a user who keeps
    rejecting can never keep the graph (and the LLM bill) running forever.
    """
    if state.get("human_approval"):
        return "final_response"
    if int(state.get("revision_count") or 0) < settings.mcp.max_revisions:
        return "revise"
    return "final_response"
