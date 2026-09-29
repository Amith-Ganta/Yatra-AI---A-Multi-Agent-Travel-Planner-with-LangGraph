# Agents & LangGraph Specification

**Phase:** 3  
**Version:** 1.0  
**Status:** Implementation  
**Dependencies:** Phase 2 (config, LLM factory)

---

## Overview

This phase implements the eight-agent LangGraph supervisor model with deterministic routing, parallel execution, and HITL approval.

**Architecture:**
```
User Message
    ↓
Supervisor Agent (guardrail + routing)
    ↓ [selected_agents list]
    ├─ Flight Agent (async, MCP)
    ├─ Hotel Agent (async, MCP)
    ├─ Weather Agent (async, MCP)
    └─ Budget Agent (LLM only)
    ↓ [all outputs]
Itinerary Agent (LLM draft)
    ↓
[interrupt()] — HITL Approval
    ↓ [resume with feedback]
Final Response Agent (polish or revise)
    ↓
Trip Plan (JSON output)
```

**Principles:**
- Latency < 10s total (< 3s per agent)
- Parallel execution where possible
- Deterministic routing (no random agent selection)
- Structured outputs (Pydantic models)
- State checkpointing (PostgreSQL)

---

## 1. src/agents/state.py

**Responsibility:** Define `TravelState` TypedDict for all agent inputs/outputs.

```python
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime

class TravelState(TypedDict, total=False):
    # Input
    message: str                          # User query
    thread_id: str                        # For resumption
    
    # Supervisor output
    allowed: bool                         # Guardrail decision
    reason: str                           # Guardrail reason
    selected_agents: List[str]            # Agents to run
    trip_constraints: Dict[str, Any]      # Extracted constraints
    
    # Agent outputs (optional until filled)
    flight_output: Optional[Dict[str, Any]]
    hotel_output: Optional[Dict[str, Any]]
    weather_output: Optional[Dict[str, Any]]
    budget_output: Optional[Dict[str, Any]]
    itinerary_output: Optional[Dict[str, Any]]
    
    # HITL
    human_approval: Optional[bool]        # approve / revise
    feedback: Optional[str]               # User feedback
    
    # Final
    final_response: Dict[str, Any]        # Polished output
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    user_id: str
    model_used: str                       # Which LLM was primary
    total_tokens: int                     # Token usage
    cost_usd: float                       # Total cost
    
    # Evaluation (async, post-production)
    eval_scores: Optional[Dict[str, float]]
    eval_passed: Optional[bool]
```

---

## 2. src/agents/supervisor.py

**Responsibility:** Input guardrail + agent routing logic.

```python
async def supervisor_agent(state: TravelState, llm_factory) -> Dict:
    """
    Guardrail check: is this a valid travel request?
    Extract constraints and decide which agents to run.
    
    Output JSON:
    {
      "allowed": true/false,
      "reason": "...",
      "selected_agents": ["flight", "hotel", "weather", "budget"],
      "trip_constraints": {
        "destination": "...",
        "dates": [...],
        "budget": 1000,
        "party_size": 2,
        "trip_type": "leisure|business|adventure"
      }
    }
    """
    llm = llm_factory.get_llm()
    
    # Guardrail prompt
    guardrail_prompt = """
    Is this a valid travel-planning request?
    User query: {message}
    
    Respond with JSON:
    {{
      "allowed": true or false,
      "reason": "short explanation",
      "selected_agents": ["flight", "hotel", "weather", "budget"],
      "trip_constraints": {{...}}
    }}
    """
    
    response = await llm.ainvoke(guardrail_prompt.format(message=state["message"]))
    # Parse JSON from response
    # Return output dict
```

**Routing Logic:**
- Always run: flight (if any trip), itinerary, final_response
- Conditionally run:
  - hotel: if trip_duration > 1 day
  - weather: if trip_duration > 7 days
  - budget: if budget explicitly mentioned

---

## 3. src/agents/workers/

**Seven specialist agents (async, parallel where possible):**

### 3.1 Flight Agent
```python
async def flight_agent(state: TravelState, mcp_tools) -> Dict:
    """Fetch flight data via AviationStack MCP."""
    # Extract from state: destination, dates, budget, party_size
    # Call MCP: get_flights(destination, dates, budget)
    # LLM: rank airlines, explain booking advice
    # Return: { flights: [...], best_option: {...}, advice: str }
    # Latency: < 2s (MCP + LLM)
```

### 3.2 Hotel Agent
```python
async def hotel_agent(state: TravelState, mcp_tools) -> Dict:
    """Fetch hotel options via Tavily MCP."""
    # Extract: destination, dates, budget, preferences
    # Call MCP: search_hotels(destination, dates, budget)
    # LLM: summarize neighborhoods, recommend
    # Return: { hotels: [...], neighborhoods: [...], recommendations: str }
    # Latency: < 2s
```

### 3.3 Weather Agent
```python
async def weather_agent(state: TravelState, mcp_tools) -> Dict:
    """Fetch weather via OpenWeatherMap (or Open-Meteo)."""
    # Extract: destination, dates
    # Call MCP: get_weather_forecast(destination, dates)
    # Return: { current: {...}, forecast: [...], packing_advice: str }
    # Latency: < 1s (mostly MCP data)
```

### 3.4 Budget Agent
```python
async def budget_agent(state: TravelState, llm_factory) -> Dict:
    """Calculate budget breakdown (LLM only)."""
    # Input: all prior agent outputs
    # LLM: "Given flights, hotels, weather, calculate costs..."
    # Return: { categories: {...}, total: 1000, feasibility: bool, advice: str }
    # Latency: < 1s (LLM only, small input)
```

### 3.5 Itinerary Agent
```python
async def itinerary_agent(state: TravelState, llm_factory) -> Dict:
    """Draft day-by-day itinerary."""
    # Input: destination, dates, flights, hotels, weather, budget
    # LLM: "Create a day-by-day trip plan that:"
    #       "- Respects flight times and hotel check-in/out"
    #       "- Includes must-see attractions and restaurants"
    #       "- Balances activities, rest, and budget"
    # Return: { itinerary: [day1: {...}, day2: {...}, ...], highlights: [...], notes: str }
    # Latency: < 2s (complex LLM prompt)
```

### 3.6 Human Approval Agent
```python
async def human_approval_agent(state: TravelState) -> Dict:
    """Pause for human review."""
    # Call: langgraph.interrupt()
    # Pause state, return draft itinerary to user
    # Wait for: { approved: bool, feedback: str? }
    # Resume: Command(resume={...})
    # Latency: Blocking (user-driven)
```

### 3.7 Final Response Agent
```python
async def final_response_agent(state: TravelState, llm_factory) -> Dict:
    """Polish or revise based on feedback."""
    # If approved:
    #   - Format nicely (Markdown)
    #   - Add packing list, tips, emergency contacts
    # If revision requested:
    #   - Re-draft with feedback
    #   - Return to approval
    # Return: { final_plan: {...}, summary: str, share_url: str? }
    # Latency: < 2s (LLM)
```

---

## 4. src/agents/routing.py

**Responsibility:** Deterministic routing logic (no agent selection randomness).

```python
AGENT_ORDER = ["flight", "hotel", "weather", "budget", "itinerary"]

def should_run_agent(agent_name: str, selected_agents: List[str]) -> bool:
    """Determine if an agent should run."""
    # Itinerary always runs
    if agent_name == "itinerary":
        return True
    # Others only if selected by supervisor
    return agent_name in selected_agents

def get_agent_sequence(selected_agents: List[str]) -> List[str]:
    """Return agents in execution order, skipping unselected."""
    return [a for a in AGENT_ORDER if should_run_agent(a, selected_agents)]
```

---

## 5. src/agents/graph.py

**Responsibility:** Build and run LangGraph StateGraph.

```python
from langgraph.graph import StateGraph
from .state import TravelState
from .supervisor import supervisor_agent
from .workers import (
    flight_agent, hotel_agent, weather_agent, budget_agent,
    itinerary_agent, human_approval_agent, final_response_agent
)
from .routing import get_agent_sequence

async def build_graph(checkpointer, llm_factory, mcp_tools):
    """Build the complete LangGraph."""
    
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
    
    # Add edges (routing)
    graph.add_edge("START", "supervisor")
    
    # Conditional: supervisor → workers
    def route_from_supervisor(state) -> List[str]:
        if not state["allowed"]:
            return ["final_response"]  # Skip to final with rejection
        selected = state["selected_agents"]
        return get_agent_sequence(selected)
    
    graph.add_conditional_edges("supervisor", route_from_supervisor)
    
    # Parallel: workers → itinerary
    for agent in ["flight", "hotel", "weather", "budget"]:
        graph.add_edge(agent, "itinerary")
    
    # Itinerary → approval
    graph.add_edge("itinerary", "human_approval")
    
    # Approval → final
    graph.add_edge("human_approval", "final_response")
    
    # Final → END
    graph.add_edge("final_response", "END")
    
    # Set checkpointer
    return graph.compile(checkpointer=checkpointer)
```

**Latency Optimization:**
- Parallel execution: flight, hotel, weather, budget all run simultaneously (not sequentially)
- Use `asyncio.gather()` to run independent agents in parallel
- Total: ~2s (longest agent) + 2s (itinerary) = ~4s nominal, < 10s SLA

---

## 6. Testing: test_agents.py

```python
@pytest.mark.asyncio
async def test_supervisor_agent_valid_request():
    """Supervisor approves valid trip request."""
    state = {"message": "Plan a 5-day trip to Japan for 2 people, $3000 budget"}
    result = await supervisor_agent(state, llm_factory_mock)
    assert result["allowed"] == True
    assert "flight" in result["selected_agents"]

@pytest.mark.asyncio
async def test_supervisor_agent_invalid_request():
    """Supervisor rejects invalid request."""
    state = {"message": "Tell me a joke"}
    result = await supervisor_agent(state, llm_factory_mock)
    assert result["allowed"] == False

@pytest.mark.asyncio
async def test_parallel_agents():
    """Multiple agents run in parallel."""
    # Simulate flight + hotel + weather running together
    import asyncio
    start = time.time()
    results = await asyncio.gather(
        flight_agent_mock(state),
        hotel_agent_mock(state),
        weather_agent_mock(state),
    )
    elapsed = time.time() - start
    assert elapsed < 3.0  # Should complete faster than sequential

@pytest.mark.asyncio
async def test_routing_logic():
    """Routing selects correct agents."""
    selected = ["flight", "hotel"]
    sequence = get_agent_sequence(selected)
    assert "flight" in sequence
    assert "hotel" in sequence
    assert "weather" not in sequence
    assert "itinerary" in sequence  # Always included
```

---

## Success Criteria

- ✅ All 8 agents implemented
- ✅ Latency < 10s for full trip draft (< 3s per agent)
- ✅ Parallel execution (flight + hotel + weather simultaneously)
- ✅ Deterministic routing (no randomness)
- ✅ State checkpointing works
- ✅ HITL approval/revision flow
- ✅ All tests pass
- ✅ Type checking passes (pyright)

---

**Next Phase:** Phase 4 (Tools + MCP)
