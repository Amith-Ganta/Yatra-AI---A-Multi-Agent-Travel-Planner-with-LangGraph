"""Flights MCP server.

There is no free flight-pricing API, so the options are illustrative and labelled
``"source": "mock"``. The tool contract is stable, so a live provider can replace the body
later without touching the agents.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.tools import search_flights as _search_flights

mcp = FastMCP("yatra-flights", log_level="WARNING")


@mcp.tool()
async def search_flights(
    destination: str, departure_date: str, party_size: int, budget: float
) -> dict[str, Any]:
    """List sample flight options (per-person prices) for a destination and date."""
    return await _search_flights(destination, departure_date, party_size, budget)


if __name__ == "__main__":
    mcp.run(transport="stdio")
