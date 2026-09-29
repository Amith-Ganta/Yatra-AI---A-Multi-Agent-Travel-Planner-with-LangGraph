"""Tests for agents and LangGraph."""

import pytest
from datetime import datetime

from src.agents.state import TravelState
from src.agents.routing import get_agent_sequence, should_run_agent
from src.agents.graph import build_graph


def test_travel_state_creation():
    """TravelState can be created with partial data."""
    state: TravelState = {
        "message": "Plan a trip to Japan",
        "thread_id": "test-123",
        "created_at": datetime.now(),
        "user_id": "user-1",
    }
    assert state["message"] == "Plan a trip to Japan"
    assert state["thread_id"] == "test-123"


def test_should_run_agent_always_runs():
    """Itinerary and approval agents always run."""
    assert should_run_agent("itinerary", []) == True
    assert should_run_agent("human_approval", []) == True
    assert should_run_agent("final_response", []) == True


def test_should_run_agent_conditional():
    """Conditional agents only run if selected."""
    selected = ["flight", "hotel"]
    assert should_run_agent("flight", selected) == True
    assert should_run_agent("hotel", selected) == True
    assert should_run_agent("weather", selected) == False
    assert should_run_agent("budget", selected) == False


def test_get_agent_sequence():
    """Agent sequence respects order and selection."""
    selected = ["flight", "weather"]
    sequence = get_agent_sequence(selected)

    # Flight before weather
    assert sequence.index("flight") < sequence.index("weather")

    # Itinerary always included
    assert "itinerary" in sequence

    # Unselected agents excluded
    assert "hotel" not in sequence
    assert "budget" not in sequence


def test_get_agent_sequence_all():
    """All agents included if all selected."""
    selected = ["flight", "hotel", "weather", "budget"]
    sequence = get_agent_sequence(selected)

    for agent in ["flight", "hotel", "weather", "budget", "itinerary"]:
        assert agent in sequence


def test_graph_builds():
    """LangGraph compiles without error."""
    graph = build_graph()
    assert graph is not None

    # Graph should have nodes
    assert hasattr(graph, "invoke") or hasattr(graph, "ainvoke")


@pytest.mark.asyncio
async def test_graph_handles_rejected_request():
    """Graph handles rejected (invalid) request."""
    # Note: This would require mocking LLM to return "allowed=false"
    # Placeholder for full integration test in Phase 6
    pass
