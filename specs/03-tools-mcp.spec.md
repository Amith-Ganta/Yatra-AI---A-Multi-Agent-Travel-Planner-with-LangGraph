# Tools & MCP Specification

**Phase:** 4  
**Version:** 1.0  
**Status:** Implementation  
**Dependencies:** Phase 2 (config), Phase 3 (agents)

---

## Overview

This phase integrates Model Context Protocol (MCP) for tool access. Three external data sources + one local weather service.

**Architecture:**
```
Agent requests tool
  ↓
Tool wrapper (tavily_tool, aviation_tool, weather_tool)
  ↓
MCP Client (abstracts protocol)
  ↓
External service (Tavily, AviationStack, Open-Meteo)
  ↓
Structured output (Pydantic model)
  ↓
Agent receives result
```

---

## 1. .mcp.json

**Configuration file for MCP servers.**

```json
{
  "servers": {
    "tavily-search": {
      "command": "python",
      "args": ["-m", "mcp.tools.tavily"],
      "env": {
        "TAVILY_API_KEY": "${TAVILY_API_KEY}"
      }
    },
    "aviationstack": {
      "command": "python",
      "args": ["-m", "mcp.tools.aviation"],
      "env": {
        "AVIATIONSTACK_API_KEY": "${AVIATIONSTACK_API_KEY}"
      }
    },
    "open-meteo": {
      "command": "python",
      "args": ["-m", "mcp.tools.weather"],
      "env": {}
    }
  }
}
```

---

## 2. src/tools/tavily_tool.py

**Web search via Tavily MCP.**

```python
from pydantic import BaseModel

class TavilySearchResult(BaseModel):
    query: str
    results: list[dict]  # {title, url, snippet}
    query_cost: float

async def search_hotels(destination: str, budget: float) -> TavilySearchResult:
    """Search for hotels in destination within budget."""
    # Call MCP: tavily.search(f"best hotels {destination} ${budget}")
    # Parse results, return structured output
```

---

## 3. src/tools/aviation_tool.py

**Flight data via AviationStack MCP.**

```python
class FlightSearchResult(BaseModel):
    destination: str
    departure_date: str
    flights: list[dict]  # {airline, duration, price, departure_time}
    cheapest: dict
    fastest: dict

async def search_flights(
    destination: str,
    departure_date: str,
    party_size: int,
    budget: float
) -> FlightSearchResult:
    """Search for flights via AviationStack."""
    # Call MCP: aviationstack.search(...)
    # Return parsed flights
```

---

## 4. src/tools/weather_tool.py

**Weather forecast via Open-Meteo (FREE, no key).**

```python
class WeatherForecast(BaseModel):
    location: str
    current: dict  # {temperature, condition, humidity}
    forecast: list[dict]  # [day1: {...}, day2: {...}, ...]
    packing_advice: str

async def get_weather(destination: str, start_date: str, end_date: str) -> WeatherForecast:
    """Fetch weather via Open-Meteo API (free)."""
    # Call: https://api.open-meteo.com/v1/forecast?...
    # No API key needed
    # Return structured forecast + packing tips
```

---

## 5. src/tools/__init__.py

**Tool registry and unified interface.**

```python
from .tavily_tool import search_hotels
from .aviation_tool import search_flights
from .weather_tool import get_weather

__all__ = ["search_hotels", "search_flights", "get_weather"]
```

---

## 6. src/mcp/client.py

**MCP client abstraction (low-level protocol).**

```python
class MCPClient:
    """Unified MCP client for tool access."""
    
    def __init__(self, config: dict):
        self.config = config
        self.servers = {}
    
    async def call_tool(self, server: str, tool: str, args: dict) -> dict:
        """Call a tool on an MCP server."""
        # Connect to server, invoke tool, return result
```

---

## 7. src/mcp/registry.py

**Tool registry with caching and deduplication.**

```python
class ToolRegistry:
    """Registry of available tools."""
    
    def __init__(self):
        self.tools = {}
        self._cache = {}
    
    def register(self, name: str, func, schema: dict):
        """Register a tool."""
        self.tools[name] = {"func": func, "schema": schema}
    
    async def call(self, tool_name: str, **kwargs) -> dict:
        """Call a tool, with caching."""
        # Check cache, call tool, cache result, return
```

---

## Testing

```python
# test_tools.py: 5-10 tests
@pytest.mark.asyncio
async def test_search_hotels():
    """Search hotels returns structured result."""
    result = await search_hotels("Paris", 1000)
    assert result.destination == "Paris"
    assert len(result.results) > 0

@pytest.mark.asyncio
async def test_weather_no_api_key():
    """Weather works without API key (Open-Meteo)."""
    result = await get_weather("Tokyo", "2025-03-01", "2025-03-07")
    assert result.location == "Tokyo"
    assert len(result.forecast) >= 7
```

---

## Success Criteria

- ✅ .mcp.json valid and complete
- ✅ All three tool wrappers functional
- ✅ MCP client abstracts protocol
- ✅ Tool registry with caching
- ✅ No API keys hardcoded (env-driven)
- ✅ Tests pass
- ✅ Integration with agents (Phase 3) works

---

**Next Phase:** Phase 5 (Memory + PostgreSQL)
