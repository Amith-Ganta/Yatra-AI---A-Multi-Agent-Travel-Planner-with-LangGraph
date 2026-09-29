"""Tools for travel planning agents."""

from typing import Any
import httpx
import logging

logger = logging.getLogger(__name__)


async def search_hotels(destination: str, budget: float) -> dict[str, Any]:
    """Search hotels via Tavily API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.tavily.com/search",
                params={
                    "query": f"hotels in {destination} under ${budget}",
                    "topic": "general",
                    "include_answer": True,
                },
            )
            if response.status_code == 200:
                data = response.json()
                hotels = []
                if "results" in data:
                    for result in data["results"][:5]:
                        hotels.append({
                            "name": result.get("title", "Unknown"),
                            "description": result.get("snippet", ""),
                            "url": result.get("url", ""),
                        })
                return {
                    "destination": destination,
                    "budget": budget,
                    "hotels": hotels,
                    "status": "success",
                }
    except Exception as e:
        logger.error(f"Hotel search failed: {e}")

    return {
        "destination": destination,
        "budget": budget,
        "hotels": [],
        "status": "error",
    }


async def search_flights(destination: str, departure_date: str, party_size: int, budget: float) -> dict[str, Any]:
    """Search flights via mock data (AviationStack requires paid API)."""
    flights = [
        {
            "airline": "Emirates",
            "departure": "10:00 AM",
            "arrival": "6:30 PM",
            "price": min(budget * 0.4, 450),
            "duration": "8h 30m",
        },
        {
            "airline": "Qatar Airways",
            "departure": "2:15 PM",
            "arrival": "11:45 PM",
            "price": min(budget * 0.45, 500),
            "duration": "9h 30m",
        },
        {
            "airline": "Air India",
            "departure": "11:30 PM",
            "arrival": "5:00 AM",
            "price": min(budget * 0.35, 350),
            "duration": "8h 30m",
        },
    ]

    best = min(flights, key=lambda x: x["price"])

    return {
        "destination": destination,
        "departure_date": departure_date,
        "party_size": party_size,
        "budget": budget,
        "flights": flights,
        "best_option": best,
        "status": "success",
    }


async def get_weather(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Get weather forecast via Open-Meteo API (free, no key required)."""
    coordinates = {
        "paris": (48.8566, 2.3522),
        "london": (51.5074, -0.1278),
        "tokyo": (35.6762, 139.6503),
        "sydney": (-33.8688, 151.2093),
        "barcelona": (41.3851, 2.1734),
        "new york": (40.7128, -74.0060),
        "dubai": (25.2048, 55.2708),
        "singapore": (1.3521, 103.8198),
    }

    lat, lon = coordinates.get(destination.lower(), (0, 0))

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                    "timezone": "auto",
                },
            )
            if response.status_code == 200:
                data = response.json()
                forecast = []
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                temps_max = daily.get("temperature_2m_max", [])
                temps_min = daily.get("temperature_2m_min", [])

                for i, date in enumerate(dates[:7]):
                    forecast.append({
                        "date": date,
                        "temp_max": temps_max[i] if i < len(temps_max) else 20,
                        "temp_min": temps_min[i] if i < len(temps_min) else 15,
                        "condition": "Partly Cloudy",
                    })

                packing_advice = "Bring light layers and sunscreen."
                if any(t < 10 for t in temps_min):
                    packing_advice = "Bring winter clothing and umbrella."

                return {
                    "destination": destination,
                    "start_date": start_date,
                    "end_date": end_date,
                    "forecast": forecast,
                    "packing_advice": packing_advice,
                    "status": "success",
                }
    except Exception as e:
        logger.error(f"Weather forecast failed: {e}")

    return {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "forecast": [],
        "packing_advice": "Check local weather before packing.",
        "status": "error",
    }


__all__ = ["search_hotels", "search_flights", "get_weather"]
