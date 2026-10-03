"""Hotels MCP server: hotel search through the Tavily search API (needs TAVILY_API_KEY)."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.tools import search_hotels as _search_hotels

mcp = FastMCP("yatra-hotels", log_level="WARNING")


@mcp.tool()
async def search_hotels(destination: str, budget: float) -> dict[str, Any]:
    """Find well-reviewed hotels in a destination for a total trip budget in USD."""
    return await _search_hotels(destination, budget)


if __name__ == "__main__":
    mcp.run(transport="stdio")
