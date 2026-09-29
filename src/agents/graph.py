"""LangGraph StateGraph for travel planning."""

from datetime import datetime
from langgraph.graph import StateGraph, END

from src.agents.state import TravelState
from src.agents.supervisor import supervisor_agent
from src.agents.routing import (
    route_from_supervisor,
    route_from_workers,
    route_from_approval,
)


async def flight_agent(state: TravelState) -> dict:
    """Flight research agent (placeholder)."""
    return {
        "flight_output": {
            "flights": [],
            "best_option": None,
            "advice": "Flight search would be implemented in Phase 4 with MCP tools.",
        }
    }


async def hotel_agent(state: TravelState) -> dict:
    """Hotel research agent (placeholder)."""
    return {
        "hotel_output": {
            "hotels": [],
            "neighborhoods": [],
            "recommendations": "Hotel search would be implemented in Phase 4.",
        }
    }


async def weather_agent(state: TravelState) -> dict:
    """Weather forecast agent (placeholder)."""
    return {
        "weather_output": {
            "current": {},
            "forecast": [],
            "packing_advice": "Weather data would be fetched in Phase 4.",
        }
    }


async def budget_agent(state: TravelState) -> dict:
    """Budget calculation agent (placeholder)."""
    return {
        "budget_output": {
            "categories": {},
            "total": 0,
            "feasibility": True,
            "advice": "Budget would be calculated in Phase 4.",
        }
    }


async def itinerary_agent(state: TravelState) -> dict:
    """Itinerary drafting agent (placeholder)."""
    return {
        "itinerary_output": {
            "itinerary": [],
            "highlights": [],
            "notes": "Full itinerary would be generated from collected data.",
        }
    }


async def human_approval_agent(state: TravelState) -> dict:
    """Human approval step (HITL interrupt)."""
    # In production, this would call langgraph.interrupt()
    # For now, auto-approve to continue execution
    return {
        "human_approval": True,
        "feedback": "",
    }


async def final_response_agent(state: TravelState) -> dict:
    """Final response polish."""
    return {
        "final_response": {
            "plan": state.get("itinerary_output", {}),
            "summary": "Trip plan complete.",
            "share_url": None,
        }
    }


def build_graph():
    """Build the complete LangGraph StateGraph."""
    graph = StateGraph(TravelState)

    # Add nodes
    graph.add_node("supervisor", supervisor_agent)
    graph.add_node("flight", flight_agent)
    graph.add_node("hotel", hotel_agent)
    graph.add_node("weather", weather_agent)
    graph.add_node("budget", budget_agent)
    graph.add_node("itinerary", itinerary_agent)
    graph.add_node("human_approval", human_approval_agent)
    graph.add_node("final_response", final_response_agent)

    # Entry point
    graph.set_entry_point("supervisor")

    # Supervisor routing
    graph.add_conditional_edges("supervisor", route_from_supervisor)

    # Worker edges
    for worker in ["flight", "hotel", "weather", "budget"]:
        graph.add_edge(worker, "itinerary")

    # Itinerary → Approval
    graph.add_edge("itinerary", "human_approval")

    # Approval routing
    graph.add_conditional_edges("human_approval", route_from_approval)

    # Final → End
    graph.add_edge("final_response", END)

    return graph.compile()
