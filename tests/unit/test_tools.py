"""Tests for the travel tools.

HTTP is replaced by httpx.MockTransport, so these tests never touch the network and can
inspect exactly what each tool sends.
"""

import json
from datetime import date, timedelta

import httpx
import pytest

import src.tools as tools
from src.tools import get_weather, search_flights, search_hotels


def _install_transport(monkeypatch, handler):
    """Route every tool HTTP call through ``handler``; return the list of seen requests."""
    seen: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        tools,
        "_http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(recording_handler)),
    )
    return seen


# --------------------------------------------------------------------------- hotels


@pytest.mark.asyncio
async def test_hotels_without_key_makes_no_network_call(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    seen = _install_transport(monkeypatch, lambda r: httpx.Response(500))

    result = await search_hotels("Paris", 1000.0)

    assert result["status"] == "error"
    assert result["hotels"] == []
    assert result["destination"] == "Paris"
    assert result["budget"] == 1000.0
    assert seen == []


@pytest.mark.asyncio
async def test_hotels_sends_authenticated_post_and_maps_content(monkeypatch):
    """F-hotel: the old code sent an unauthenticated GET and read a non-existent 'snippet'."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    seen = _install_transport(
        monkeypatch,
        lambda r: httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Hotel Roma",
                        "content": "  Central   and quiet ",
                        "url": "https://a",
                    },
                    {"title": "", "content": "x" * 500, "url": "https://b"},
                ]
            },
        ),
    )

    result = await search_hotels("Rome", 2000.0)

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.tavily.com/search"
    assert request.headers["authorization"] == "Bearer tvly-test"
    body = json.loads(request.content)
    assert "Rome" in body["query"]
    assert body["max_results"] == 5

    assert result["status"] == "success"
    assert result["hotels"][0] == {
        "name": "Hotel Roma",
        "description": "Central and quiet",
        "url": "https://a",
    }
    assert result["hotels"][1]["name"] == "Unknown"
    assert len(result["hotels"][1]["description"]) <= 240


@pytest.mark.asyncio
async def test_hotels_provider_error_is_reported_without_leaking_details(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret-value")
    _install_transport(monkeypatch, lambda r: httpx.Response(401, text="bad key tvly-secret-value"))

    result = await search_hotels("Rome", 500.0)

    assert result["status"] == "error"
    assert result["hotels"] == []
    assert "tvly-secret-value" not in json.dumps(result)


@pytest.mark.asyncio
async def test_hotels_network_failure_returns_error(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    def boom(request):
        raise httpx.ConnectError("no route")

    _install_transport(monkeypatch, boom)
    result = await search_hotels("Rome", 500.0)
    assert result["status"] == "error"
    assert "no route" not in json.dumps(result)


# -------------------------------------------------------------------------- flights


@pytest.mark.asyncio
async def test_flights_are_labelled_as_mock_and_per_person():
    result = await search_flights("London", "2026-12-01", 2, 750.0)
    assert result["source"] == "mock"
    assert result["status"] == "success"
    assert result["party_size"] == 2
    assert result["best_option"] == min(result["flights"], key=lambda f: f["price"])


@pytest.mark.asyncio
async def test_flight_prices_never_exceed_the_budget():
    result = await search_flights("Anywhere", "2026-12-01", 1, 100.0)
    assert all(f["price"] <= 100.0 for f in result["flights"])


# ------------------------------------------------------------------------- weather

DAILY = {
    "time": ["2026-10-02", "2026-10-03"],
    "temperature_2m_max": [24.26, 18.0],
    "temperature_2m_min": [15.0, 11.04],
    "precipitation_sum": [0.0, 6.2],
    "weather_code": [0, 63],
}


def _weather_handler(daily=None, geocode_results=None):
    geocode_results = (
        [{"name": "Rome", "country": "Italy", "latitude": 41.89, "longitude": 12.48}]
        if geocode_results is None
        else geocode_results
    )

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={"results": geocode_results})
        return httpx.Response(200, json={"daily": daily or DAILY})

    return handler


@pytest.mark.asyncio
async def test_weather_geocodes_any_city_and_queries_the_trip_dates(monkeypatch):
    """The old code used 8 hardcoded cities, fell back to (0, 0) and ignored the dates."""
    seen = _install_transport(monkeypatch, _weather_handler())
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=1)

    result = await get_weather("Rome", start.isoformat(), end.isoformat())

    geocode, forecast = seen
    assert dict(geocode.url.params)["name"] == "Rome"
    params = dict(forecast.url.params)
    assert forecast.url.host == "api.open-meteo.com"
    assert params["latitude"] == "41.89" and params["longitude"] == "12.48"
    assert params["start_date"] == start.isoformat()
    assert params["end_date"] == end.isoformat()
    assert result["status"] == "success"
    assert result["source"] == "forecast"
    assert result["location"] == "Rome, Italy"


@pytest.mark.asyncio
async def test_weather_maps_wmo_codes_instead_of_hardcoded_condition(monkeypatch):
    _install_transport(monkeypatch, _weather_handler())
    start = date.today() + timedelta(days=1)

    result = await get_weather("Rome", start.isoformat(), (start + timedelta(days=1)).isoformat())

    conditions = [day["condition"] for day in result["forecast"]]
    assert conditions == ["Clear sky", "Moderate rain"]
    assert result["forecast"][0]["temp_max"] == 24.3  # rounded
    assert "umbrella" in result["packing_advice"]


@pytest.mark.asyncio
async def test_weather_far_future_uses_last_years_conditions_on_trip_dates(monkeypatch):
    seen = _install_transport(monkeypatch, _weather_handler())
    start = date.today() + timedelta(days=90)
    end = start + timedelta(days=1)

    result = await get_weather("Rome", start.isoformat(), end.isoformat())

    archive = seen[1]
    assert archive.url.host == "archive-api.open-meteo.com"
    assert dict(archive.url.params)["start_date"] == start.replace(year=start.year - 1).isoformat()
    assert result["source"] == "typical_conditions_last_year"
    # Dates in the response are the traveller's dates, not last year's.
    assert result["forecast"][0]["date"] == start.isoformat()
    assert result["forecast"][1]["date"] == end.isoformat()


@pytest.mark.asyncio
async def test_weather_unknown_city_is_an_error_not_the_middle_of_the_ocean(monkeypatch):
    seen = _install_transport(monkeypatch, _weather_handler(geocode_results=[]))
    start = date.today() + timedelta(days=1)

    result = await get_weather("Nowhereville", start.isoformat(), start.isoformat())

    assert result["status"] == "error"
    assert result["forecast"] == []
    assert len(seen) == 1  # stopped after the failed geocode, never asked for a forecast


@pytest.mark.asyncio
async def test_weather_trip_straddling_the_horizon_gets_a_forecast_for_the_covered_days(
    monkeypatch,
):
    seen = _install_transport(monkeypatch, _weather_handler())
    start = date.today() + timedelta(days=1)

    result = await get_weather("Rome", start.isoformat(), (start + timedelta(days=60)).isoformat())

    forecast_request = seen[1]
    assert forecast_request.url.host == "api.open-meteo.com"
    requested_end = date.fromisoformat(dict(forecast_request.url.params)["end_date"])
    assert requested_end == date.today() + timedelta(days=tools.FORECAST_HORIZON_DAYS)
    assert result["source"] == "forecast"


@pytest.mark.asyncio
async def test_weather_far_future_long_trip_is_capped_at_the_provider_limit(monkeypatch):
    seen = _install_transport(monkeypatch, _weather_handler())
    start = date.today() + timedelta(days=90)

    await get_weather("Rome", start.isoformat(), (start + timedelta(days=60)).isoformat())

    params = dict(seen[1].url.params)
    span = date.fromisoformat(params["end_date"]) - date.fromisoformat(params["start_date"])
    assert span.days == tools.MAX_FORECAST_DAYS - 1


@pytest.mark.asyncio
@pytest.mark.parametrize("start, end", [("not-a-date", "2026-12-01"), ("2026-12-05", "2026-12-01")])
async def test_weather_bad_dates_return_error_without_network(monkeypatch, start, end):
    seen = _install_transport(monkeypatch, _weather_handler())
    result = await get_weather("Rome", start, end)
    assert result["status"] == "error"
    assert seen == []


@pytest.mark.asyncio
async def test_weather_provider_failure_returns_error(monkeypatch):
    def handler(request):
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(
                200, json={"results": [{"name": "Rome", "latitude": 1, "longitude": 2}]}
            )
        return httpx.Response(400, json={"reason": "out of range"})

    _install_transport(monkeypatch, handler)
    start = date.today() + timedelta(days=1)
    result = await get_weather("Rome", start.isoformat(), start.isoformat())
    assert result["status"] == "error"
    assert result["forecast"] == []


def test_packing_advice_reflects_the_forecast():
    assert "coat" in tools._packing_advice([-3], [4], [71])
    assert "boots" in tools._packing_advice([-3], [4], [71])
    assert "sunscreen" in tools._packing_advice([22], [34], [0])
    assert "umbrella" in tools._packing_advice([15], [20], [61])
    assert "Check" in tools._packing_advice([], [], [])
