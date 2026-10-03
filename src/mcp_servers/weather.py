"""Weather MCP server: forecast and climate summary from Open-Meteo (no API key)."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.tools import get_weather as _get_weather

mcp = FastMCP("yatra-weather", log_level="WARNING")


@mcp.tool()
async def get_weather(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Weather summary for a destination and trip dates (YYYY-MM-DD), with packing advice."""
    return await _get_weather(destination, start_date, end_date)


if __name__ == "__main__":
    mcp.run(transport="stdio")
