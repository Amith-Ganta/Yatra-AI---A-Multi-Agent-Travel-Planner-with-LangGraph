"""Tools for travel planning agents."""

from typing import Any

# Placeholder functions (real implementations in Phase 4+)

async def search_hotels(destination: str, budget: float) -> dict[str, Any]:
    """Search hotels via Tavily."""
    return {
        "destination": destination,
        "budget": budget,
        "hotels": [],
        "status": "Phase 4: MCP integration pending",
    }


async def search_flights(destination: str, departure_date: str, party_size: int, budget: float) -> dict[str, Any]:
    """Search flights via AviationStack."""
    return {
        "destination": destination,
        "departure_date": departure_date,
        "party_size": party_size,
        "budget": budget,
        "flights": [],
        "status": "Phase 4: MCP integration pending",
    }


async def get_weather(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Get weather forecast via Open-Meteo."""
    return {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "forecast": [],
        "status": "Phase 4: MCP integration pending",
    }


__all__ = ["search_hotels", "search_flights", "get_weather"]
