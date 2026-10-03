"""Tools for travel planning agents.

Every tool returns a dict with a ``status`` of "success" or "error" and never raises, so a
failing provider degrades one section of the plan instead of the whole request.
"""

import logging
import os
from datetime import date, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 10.0

TAVILY_URL = "https://api.tavily.com/search"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Open-Meteo serves a real forecast for about 16 days ahead.
FORECAST_HORIZON_DAYS = 15
MAX_FORECAST_DAYS = 16

# WMO weather interpretation codes, as documented by Open-Meteo.
WMO_CONDITIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

_WET_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
_SNOW_CODES = {71, 73, 75, 77, 85, 86}


def _http_client() -> httpx.AsyncClient:
    """HTTP client factory (a single seam that tests replace with a mock transport)."""
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)


def _short(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


async def search_hotels(destination: str, budget: float) -> dict[str, Any]:
    """Search hotels via the Tavily search API (needs TAVILY_API_KEY)."""
    result: dict[str, Any] = {
        "destination": destination,
        "budget": budget,
        "hotels": [],
        "status": "error",
    }

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.warning("TAVILY_API_KEY is not set; skipping hotel search")
        result["error"] = "Hotel search is not configured."
        return result

    payload = {
        "query": f"best rated hotels in {destination} for a trip budget of ${budget:.0f}",
        "topic": "general",
        "search_depth": "basic",
        "max_results": 5,
    }
    try:
        async with _http_client() as client:
            response = await client.post(
                TAVILY_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.status_code != 200:
            logger.error("Tavily returned HTTP %s", response.status_code)
            result["error"] = "Hotel search provider returned an error."
            return result

        data = response.json()
        result["hotels"] = [
            {
                "name": item.get("title") or "Unknown",
                "description": _short(item.get("content", "")),
                "url": item.get("url", ""),
            }
            for item in data.get("results", [])[:5]
        ]
        result["status"] = "success"
    except Exception as exc:
        logger.error("Hotel search failed: %s", exc)
        result["error"] = "Hotel search is temporarily unavailable."
    return result


async def search_flights(
    destination: str, departure_date: str, party_size: int, budget: float
) -> dict[str, Any]:
    """Return sample flight options.

    There is no free flight-pricing API, so these are illustrative mock options and are
    labelled ``"source": "mock"`` so the UI and the budget agent never present them as live
    fares. Prices are per person.
    """
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
        "source": "mock",
    }


def _packing_advice(temps_min: list[float], temps_max: list[float], codes: list[int]) -> str:
    """Practical packing advice from the forecast numbers."""
    if not temps_min or not temps_max:
        return "Check the local weather before packing."

    coldest, warmest = min(temps_min), max(temps_max)
    tips: list[str] = []

    if coldest < 5:
        tips.append("a warm coat, hat and gloves")
    elif coldest < 12:
        tips.append("a warm jacket and layers")
    elif warmest > 28:
        tips.append("light breathable clothing, sunscreen and a hat")
    else:
        tips.append("light layers for changing temperatures")

    if any(code in _SNOW_CODES for code in codes):
        tips.append("waterproof boots for snow")
    if any(code in _WET_CODES for code in codes):
        tips.append("an umbrella or rain jacket")

    return "Pack " + ", ".join(tips) + "."


def _same_dates_last_year(start: date, end: date) -> tuple[date, date]:
    """Shift a date range back one year (29 Feb falls back to 28 Feb)."""

    def shift(day: date) -> date:
        try:
            return day.replace(year=day.year - 1)
        except ValueError:
            return day.replace(year=day.year - 1, day=28)

    return shift(start), shift(end)


async def _geocode(client: httpx.AsyncClient, destination: str) -> Optional[dict[str, Any]]:
    response = await client.get(
        GEOCODING_URL, params={"name": destination, "count": 1, "language": "en"}
    )
    if response.status_code != 200:
        return None
    results: list[dict[str, Any]] = response.json().get("results") or []
    return results[0] if results else None


async def get_weather(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Weather for the trip dates via Open-Meteo (free, no key required).

    Any city is geocoded first. Trips inside the forecast horizon get a real forecast; trips
    further out get what the weather was on the same dates last year, labelled as such,
    because a 16-day forecast cannot cover a trip planned weeks ahead.
    """
    result: dict[str, Any] = {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "forecast": [],
        "packing_advice": "Check the local weather before packing.",
        "status": "error",
    }

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if end < start:
            raise ValueError("end_date is before start_date")
        horizon = date.today() + timedelta(days=FORECAST_HORIZON_DAYS)
        within_horizon = start <= horizon
        # A real forecast stops at the horizon; archive lookups are capped at the same length.
        end = min(end, horizon if within_horizon else start + timedelta(days=MAX_FORECAST_DAYS - 1))

        async with _http_client() as client:
            place = await _geocode(client, destination)
            if place is None:
                result["error"] = f"Could not find '{destination}' on the map."
                return result

            if within_horizon:
                url, source = FORECAST_URL, "forecast"
                query_start, query_end = start, end
            else:
                url, source = ARCHIVE_URL, "typical_conditions_last_year"
                query_start, query_end = _same_dates_last_year(start, end)

            response = await client.get(
                url,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                    "start_date": query_start.isoformat(),
                    "end_date": query_end.isoformat(),
                    "timezone": "auto",
                },
            )
        if response.status_code != 200:
            logger.error("Open-Meteo returned HTTP %s", response.status_code)
            result["error"] = "Weather provider returned an error."
            return result

        daily = response.json().get("daily", {})
        dates = daily.get("time", [])
        maxima = daily.get("temperature_2m_max", [])
        minima = daily.get("temperature_2m_min", [])
        rain = daily.get("precipitation_sum", [])
        codes = daily.get("weather_code", [])

        forecast: list[dict[str, Any]] = []
        for index, _ in enumerate(dates):
            if index >= len(maxima) or index >= len(minima):
                break
            if maxima[index] is None or minima[index] is None:
                continue
            code = codes[index] if index < len(codes) and codes[index] is not None else None
            # Report the date the traveller will actually be there, not last year's date.
            trip_day = start + timedelta(days=index)
            forecast.append(
                {
                    "date": trip_day.isoformat(),
                    "temp_max": round(maxima[index], 1),
                    "temp_min": round(minima[index], 1),
                    "precipitation_mm": rain[index] if index < len(rain) else None,
                    "condition": (
                        WMO_CONDITIONS.get(code, "Unknown") if code is not None else "Unknown"
                    ),
                }
            )

        if not forecast:
            result["error"] = "Weather provider returned no data for these dates."
            return result

        used_codes = [c for c in codes if c is not None]
        result.update(
            {
                "location": ", ".join(
                    part for part in (place.get("name"), place.get("country")) if part
                ),
                "source": source,
                "forecast": forecast,
                "packing_advice": _packing_advice(
                    [d["temp_min"] for d in forecast],
                    [d["temp_max"] for d in forecast],
                    used_codes,
                ),
                "status": "success",
            }
        )
    except Exception as exc:
        logger.error("Weather lookup failed: %s", exc)
        result["error"] = "Weather is temporarily unavailable."
    return result


__all__ = ["search_hotels", "search_flights", "get_weather"]
