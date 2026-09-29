"""Tests for travel planning tools (MCP wrappers)."""

import pytest
from src.tools import search_hotels, search_flights, get_weather


@pytest.mark.asyncio
async def test_search_hotels_signature():
    """Search hotels accepts destination and budget."""
    result = await search_hotels("Paris", 1000.0)
    assert isinstance(result, dict)
    assert "destination" in result
    assert result["destination"] == "Paris"
    assert "budget" in result
    assert result["budget"] == 1000.0


@pytest.mark.asyncio
async def test_search_hotels_returns_structure():
    """Search hotels returns expected structure."""
    result = await search_hotels("Tokyo", 2000.0)
    assert "hotels" in result
    assert isinstance(result["hotels"], list)
    assert "status" in result


@pytest.mark.asyncio
async def test_search_flights_signature():
    """Search flights accepts all required parameters."""
    result = await search_flights("NYC", "2025-03-15", 2, 500.0)
    assert isinstance(result, dict)
    assert result["destination"] == "NYC"
    assert result["departure_date"] == "2025-03-15"
    assert result["party_size"] == 2
    assert result["budget"] == 500.0


@pytest.mark.asyncio
async def test_search_flights_returns_structure():
    """Search flights returns expected structure."""
    result = await search_flights("London", "2025-04-01", 1, 750.0)
    assert "flights" in result
    assert isinstance(result["flights"], list)
    assert "status" in result


@pytest.mark.asyncio
async def test_get_weather_signature():
    """Get weather accepts destination and date range."""
    result = await get_weather("Barcelona", "2025-03-01", "2025-03-07")
    assert isinstance(result, dict)
    assert result["destination"] == "Barcelona"
    assert result["start_date"] == "2025-03-01"
    assert result["end_date"] == "2025-03-07"


@pytest.mark.asyncio
async def test_get_weather_returns_structure():
    """Get weather returns expected structure."""
    result = await get_weather("Sydney", "2025-02-01", "2025-02-10")
    assert "forecast" in result
    assert isinstance(result["forecast"], list)
    assert "status" in result
