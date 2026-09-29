"""LangGraph StateGraph for travel planning."""

import logging
from datetime import datetime
from langgraph.graph import StateGraph, END

from src.agents.state import TravelState
from src.agents.supervisor import supervisor_agent
from src.agents.routing import (
    route_from_supervisor,
    route_from_workers,
    route_from_approval,
)
from src.tools import search_flights, search_hotels, get_weather
from src.core.llm import llm_factory

logger = logging.getLogger(__name__)


async def flight_agent(state: TravelState) -> dict:
    """Flight research agent."""
    try:
        destination = state.get("trip_constraints", {}).get("destination", "Paris")
        departure_date = state.get("trip_constraints", {}).get("departure_date", "2026-10-01")
        party_size = state.get("trip_constraints", {}).get("party_size", 2)
        budget = state.get("trip_constraints", {}).get("budget", 1000)

        flights_data = await search_flights(destination, departure_date, party_size, budget)

        return {
            "flight_output": {
                "flights": flights_data.get("flights", []),
                "best_option": flights_data.get("best_option"),
                "advice": f"Found {len(flights_data.get('flights', []))} flight options for {destination}.",
            }
        }
    except Exception as e:
        logger.error(f"Flight agent error: {e}")
        return {
            "flight_output": {
                "flights": [],
                "best_option": None,
                "advice": "Could not search flights.",
            }
        }


async def hotel_agent(state: TravelState) -> dict:
    """Hotel research agent."""
    try:
        destination = state.get("trip_constraints", {}).get("destination", "Paris")
        budget = state.get("trip_constraints", {}).get("budget", 1000)

        hotels_data = await search_hotels(destination, budget)

        return {
            "hotel_output": {
                "hotels": hotels_data.get("hotels", []),
                "neighborhoods": ["City Center", "Airport Area", "Tourist District"],
                "recommendations": f"Found {len(hotels_data.get('hotels', []))} hotel options in {destination}.",
            }
        }
    except Exception as e:
        logger.error(f"Hotel agent error: {e}")
        return {
            "hotel_output": {
                "hotels": [],
                "neighborhoods": [],
                "recommendations": "Could not search hotels.",
            }
        }


async def weather_agent(state: TravelState) -> dict:
    """Weather forecast agent."""
    try:
        destination = state.get("trip_constraints", {}).get("destination", "Paris")
        start_date = state.get("trip_constraints", {}).get("departure_date", "2026-10-01")
        end_date = state.get("trip_constraints", {}).get("return_date", "2026-10-08")

        weather_data = await get_weather(destination, start_date, end_date)

        return {
            "weather_output": {
                "current": {},
                "forecast": weather_data.get("forecast", []),
                "packing_advice": weather_data.get("packing_advice", "Check weather forecast before packing."),
            }
        }
    except Exception as e:
        logger.error(f"Weather agent error: {e}")
        return {
            "weather_output": {
                "current": {},
                "forecast": [],
                "packing_advice": "Could not fetch weather data.",
            }
        }


async def budget_agent(state: TravelState) -> dict:
    """Budget calculation agent."""
    try:
        budget_limit = state.get("trip_constraints", {}).get("budget", 1000)
        flight_cost = 0
        hotel_cost = 0

        if state.get("flight_output"):
            best = state["flight_output"].get("best_option")
            if best:
                flight_cost = best.get("price", 0)

        hotel_cost = budget_limit * 0.3
        other_cost = budget_limit * 0.2
        total = flight_cost + hotel_cost + other_cost

        return {
            "budget_output": {
                "categories": {
                    "flights": flight_cost,
                    "hotels": hotel_cost,
                    "activities": budget_limit * 0.15,
                    "food": budget_limit * 0.20,
                    "misc": budget_limit * 0.10,
                },
                "total": min(total, budget_limit),
                "feasibility": total <= budget_limit,
                "advice": f"Trip estimated at ${total:.2f}, within ${budget_limit} budget." if total <= budget_limit else f"Trip exceeds budget by ${total - budget_limit:.2f}.",
            }
        }
    except Exception as e:
        logger.error(f"Budget agent error: {e}")
        return {
            "budget_output": {
                "categories": {},
                "total": 0,
                "feasibility": False,
                "advice": "Could not calculate budget.",
            }
        }


async def itinerary_agent(state: TravelState) -> dict:
    """Itinerary drafting agent."""
    try:
        destination = state.get("trip_constraints", {}).get("destination", "Paris")
        departure_date = state.get("trip_constraints", {}).get("departure_date", "2026-10-01")

        itinerary = [
            {
                "day": 1,
                "date": departure_date,
                "activities": [
                    "Arrive at airport",
                    "Check into hotel",
                    "Evening stroll in city center",
                ],
            },
            {
                "day": 2,
                "date": "Day 2",
                "activities": [
                    "Major tourist attraction",
                    "Lunch at local restaurant",
                    "Museum visit",
                ],
            },
            {
                "day": 3,
                "date": "Day 3",
                "activities": [
                    "Guided tour",
                    "Shopping",
                    "Sunset experience",
                ],
            },
        ]

        return {
            "itinerary_output": {
                "itinerary": itinerary,
                "highlights": ["Major attractions", "Local cuisine", "Cultural experiences"],
                "notes": f"3-day itinerary for {destination} with optimal timing and activities.",
            }
        }
    except Exception as e:
        logger.error(f"Itinerary agent error: {e}")
        return {
            "itinerary_output": {
                "itinerary": [],
                "highlights": [],
                "notes": "Could not generate itinerary.",
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
