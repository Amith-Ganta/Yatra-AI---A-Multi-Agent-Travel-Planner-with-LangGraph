"""End-to-end workflow integration tests."""

import pytest

from src.agents.graph import budget_agent, flight_agent, hotel_agent, weather_agent
from src.agents.state import TravelState
from src.memory import add_message, create_thread, get_history, get_thread


class TestAgentOutputs:
    """Test individual agent outputs conform to schema."""

    @pytest.mark.asyncio
    async def test_flight_agent_output_structure(self):
        """Flight agent returns expected structure."""
        state: TravelState = {"message": "Test", "thread_id": "test-123"}
        result = await flight_agent(state)

        assert "flight_output" in result
        assert isinstance(result["flight_output"], dict)
        assert "flights" in result["flight_output"]
        assert "advice" in result["flight_output"]

    @pytest.mark.asyncio
    async def test_hotel_agent_output_structure(self):
        """Hotel agent returns expected structure."""
        state: TravelState = {"message": "Test", "thread_id": "test-123"}
        result = await hotel_agent(state)

        assert "hotel_output" in result
        assert isinstance(result["hotel_output"], dict)
        assert "hotels" in result["hotel_output"]
        assert "recommendations" in result["hotel_output"]

    @pytest.mark.asyncio
    async def test_weather_agent_output_structure(self):
        """Weather agent returns expected structure."""
        state: TravelState = {"message": "Test", "thread_id": "test-123"}
        result = await weather_agent(state)

        assert "weather_output" in result
        assert isinstance(result["weather_output"], dict)
        assert "forecast" in result["weather_output"]
        assert "packing_advice" in result["weather_output"]

    @pytest.mark.asyncio
    async def test_budget_agent_output_structure(self):
        """Budget agent returns expected structure."""
        state: TravelState = {"message": "Test", "thread_id": "test-123"}
        result = await budget_agent(state)

        assert "budget_output" in result
        assert isinstance(result["budget_output"], dict)
        assert "total" in result["budget_output"]
        assert "feasibility" in result["budget_output"]


@pytest.mark.usefixtures("database")
class TestThreadWorkflow:
    """Test conversation thread workflow (real Postgres)."""

    @pytest.mark.asyncio
    async def test_thread_creation_and_retrieval(self):
        """Thread can be created and retrieved."""
        thread_id = await create_thread("test-user", {"destination": "Paris"})
        assert thread_id is not None

        thread = await get_thread(thread_id)
        assert thread is not None
        assert thread["user_id"] == "test-user"

    @pytest.mark.asyncio
    async def test_conversation_history_sequential(self):
        """Conversation history maintains order."""
        thread_id = await create_thread("test-user")

        await add_message(thread_id, "user", "First message")
        await add_message(thread_id, "assistant", "Response")
        await add_message(thread_id, "user", "Follow-up")

        history = await get_history(thread_id)

        assert len(history) == 3
        assert history[0]["content"] == "First message"
        assert history[1]["content"] == "Response"
        assert history[2]["content"] == "Follow-up"

    @pytest.mark.asyncio
    async def test_thread_resumption_flow(self):
        """Thread can be resumed in multiple calls."""
        thread_id = await create_thread("test-user")

        # First interaction
        await add_message(thread_id, "user", "Plan a trip")
        history_1 = await get_history(thread_id)
        assert len(history_1) == 1

        # Resume and add more
        await add_message(thread_id, "assistant", "I can help!")
        await add_message(thread_id, "user", "What's the budget?")

        history_2 = await get_history(thread_id)
        assert len(history_2) == 3

    @pytest.mark.asyncio
    async def test_conversation_with_metadata(self):
        """Messages can include metadata."""
        thread_id = await create_thread("test-user")

        metadata = {"source": "api", "version": "1.0"}
        await add_message(thread_id, "user", "Test message", metadata)

        history = await get_history(thread_id)
        assert len(history) == 1
        assert history[0]["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_thread_metadata_persistence(self):
        """Thread metadata persists across calls."""
        initial_metadata = {"destination": "Tokyo", "budget": 2000}
        thread_id = await create_thread("test-user", initial_metadata)

        thread = await get_thread(thread_id)
        assert thread["metadata"] == initial_metadata


class TestStateTransitions:
    """Test agent state transitions."""

    @pytest.mark.asyncio
    async def test_agent_preserves_input_state(self):
        """Agents preserve input state."""
        state: TravelState = {
            "message": "Test trip to Paris",
            "thread_id": "test-123",
            "user_id": "user-456",
        }

        result = await flight_agent(state)

        # Agent should return update dict, not full state
        assert isinstance(result, dict)
        assert "flight_output" in result

    @pytest.mark.asyncio
    async def test_multiple_agents_independent(self):
        """Multiple agents work independently."""
        state: TravelState = {"message": "Test", "thread_id": "test-123"}

        flight_result = await flight_agent(state)
        hotel_result = await hotel_agent(state)
        weather_result = await weather_agent(state)

        # Each agent should return its own output
        assert "flight_output" in flight_result
        assert "hotel_output" in hotel_result
        assert "weather_output" in weather_result

        # Outputs should be independent
        assert flight_result != hotel_result
        assert hotel_result != weather_result
