"""Deterministic routing logic for agents."""

AGENT_ORDER = ["flight", "hotel", "weather", "budget", "itinerary"]


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


def route_from_supervisor(state: dict) -> list[str] | str:
    """Route from supervisor based on guardrail decision."""
    if not state.get("allowed", False):
        return "final_response"  # Skip to final with rejection

    selected = state.get("selected_agents", [])
    sequence = get_agent_sequence(selected)

    # If no agents selected, skip to itinerary
    if not sequence:
        return "itinerary"

    return sequence


def route_from_workers(state: dict) -> str:
    """Route from any worker to itinerary."""
    return "itinerary"


def route_from_approval(state: dict) -> str:
    """Route from approval based on decision."""
    if state.get("human_approval"):
        return "final_response"
    else:
        # Revision requested: go back to itinerary
        return "itinerary"
