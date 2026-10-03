"""API integration tests against a real database (the app lifespan opens the pool).

Only the LLM supervisor, the revision LLM and the three network tools are faked. The graph, the
SSE streaming, the plan documents and the Postgres checkpointer are the real ones, so a paused
trip really waits for its approval in the ``checkpoints`` table.
"""

import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import src.agents.graph as graph_module
from src.agents.runtime import init_graph
from src.api import create_app
from src.api.streaming import PLANNING_FAILED
from src.core.config import settings
from src.memory import create_thread, db_pool, get_history
from src.memory.saver import checkpoint_store

# Everything the fake trip runs before the approval pause, in dependency order
PLANNING_NODES = ["supervisor", "flight", "hotel", "weather", "budget", "itinerary"]


def _events(response: Any) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _kinds(events: list[dict[str, Any]]) -> list[str]:
    return [event["type"] for event in events]


def _nodes(events: list[dict[str, Any]]) -> list[str]:
    return [event["node"] for event in events if event["type"] == "progress"]


def _one(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    found = [event for event in events if event["type"] == kind]
    assert len(found) == 1, f"expected one {kind!r} event, got {_kinds(events)}"
    return found[0]


def _rebuild_graph() -> None:
    """The lifespan compiled the graph before the test patched the agents; compile it again."""
    init_graph(checkpoint_store.saver)


def _plan(client: TestClient, message: str = "Plan a trip to Rome", **extra: Any) -> list[Any]:
    return _events(client.post("/api/plan", json={"message": message, **extra}))


def _decide(client: TestClient, thread_id: str, approved: bool, feedback: str | None = None) -> Any:
    body: dict[str, Any] = {"approved": approved}
    if feedback is not None:
        body["feedback"] = feedback
    return client.put(f"/api/threads/{thread_id}/approve", json=body)


class FakeRevisionLLM:
    """Rewrites the 3 day itinerary after a rejection."""

    async def ainvoke(self, prompt: str) -> Any:
        days = [{"day": n, "activities": ["a food tour"]} for n in range(1, 4)]
        return SimpleNamespace(content=json.dumps({"itinerary": days, "summary": "Revised."}))


@pytest.fixture
def fake_trip(monkeypatch):
    """Fake the supervisor, the revision LLM and the three network tools; the rest is real."""

    async def fake_supervisor(state):
        return {
            "allowed": True,
            "reason": "test",
            "selected_agents": ["flight", "hotel", "weather", "budget"],
            "trip_constraints": {
                "destination": "Rome",
                "start_date": "2099-05-10",
                "end_date": "2099-05-12",
                "budget_usd": 2000,
                "party_size": 2,
                "trip_type": "leisure",
            },
        }

    async def fake_flights(destination, departure_date, party_size, budget):
        flights = [{"airline": "TestAir", "price": 300.0}]
        return {"flights": flights, "best_option": flights[0], "source": "mock"}

    async def fake_hotels(destination, budget):
        return {"hotels": [{"name": "Hotel Test"}], "status": "success"}

    async def fake_weather(destination, start, end):
        return {
            "forecast": [],
            "packing_advice": "Light layers.",
            "status": "success",
            "source": "forecast",
            "location": "Rome, Italy",
        }

    monkeypatch.setattr(graph_module, "supervisor_agent", fake_supervisor)
    monkeypatch.setattr(graph_module, "search_flights", fake_flights)
    monkeypatch.setattr(graph_module, "search_hotels", fake_hotels)
    monkeypatch.setattr(graph_module, "get_weather", fake_weather)
    monkeypatch.setattr(
        graph_module, "llm_factory", SimpleNamespace(get_llm=lambda: FakeRevisionLLM())
    )


@pytest.fixture
def trip(client, fake_trip):
    """The API client with the fake trip wired into the running graph."""
    _rebuild_graph()
    return client


@pytest.fixture
def paused(trip) -> str:
    """A thread whose run is waiting for a human decision."""
    events = _plan(trip)
    assert "approval_required" in _kinds(events)
    return _one(events, "thread")["thread_id"]


class TestHealth:
    def test_health_check_lists_the_features(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok" and body["service"] == "Yatra AI"
        assert set(body["features"]) == {
            "supervisor_agent",
            "input_guardrail",
            "human_in_the_loop",
            "postgres_checkpointer",
            "mcp_tools",
        }

    def test_readiness_is_200_when_the_database_is_up(self, client):
        """The lifespan opens the pool, so /ready can really query Postgres."""
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert "mcp" in body

    def test_cors_headers_are_returned_for_a_browser_origin(self, client):
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


class TestThreads:
    def test_plan_requires_a_message(self, client):
        assert client.post("/api/plan", json={"user_id": "test"}).status_code == 422

    @pytest.mark.parametrize("thread_id", ["nonexistent-thread-id", str(uuid4())])
    def test_get_nonexistent_thread_is_404(self, client, thread_id):
        """Both a malformed id and a well-formed unknown UUID are a clean 404, never a 500."""
        assert client.get(f"/api/threads/{thread_id}").status_code == 404

    def test_plan_for_an_unknown_thread_is_404_not_a_stream(self, client):
        response = client.post("/api/plan", json={"message": "hi", "thread_id": str(uuid4())})
        assert response.status_code == 404

    def test_thread_roundtrip_through_the_api(self, client):
        thread_id = client.portal.call(create_thread, "api-user", {"destination": "Rome"})

        body = client.get(f"/api/threads/{thread_id}").json()

        assert body["thread"]["thread_id"] == thread_id
        assert body["thread"]["metadata"] == {"destination": "Rome"}
        assert body["history"] == []
        assert body["message_count"] == 0
        assert body["plan"] is None
        assert body["approval"] is None


class TestApprovalValidation:
    @pytest.mark.parametrize("thread_id", ["nonexistent-thread-id", str(uuid4())])
    def test_approve_nonexistent_thread_is_404(self, client, thread_id):
        assert _decide(client, thread_id, True).status_code == 404

    def test_the_body_needs_a_decision(self, client):
        response = client.put(f"/api/threads/{uuid4()}/approve", json={"feedback": "no decision"})
        assert response.status_code == 422

    def test_a_rejection_needs_feedback(self, client):
        thread_id = client.portal.call(create_thread, "api-user")
        for feedback in (None, "", "   "):
            assert _decide(client, thread_id, False, feedback).status_code == 400

    def test_a_thread_with_no_plan_waiting_is_409(self, client):
        thread_id = client.portal.call(create_thread, "api-user")

        response = _decide(client, thread_id, True)

        assert response.status_code == 409
        assert client.portal.call(get_history, thread_id) == []  # nothing was recorded

    def test_an_answered_plan_cannot_be_answered_twice(self, trip, paused):
        assert _decide(trip, paused, True).status_code == 200

        assert _decide(trip, paused, True).status_code == 409


class TestPlanStream:
    def test_the_stream_runs_every_agent_once_and_pauses_for_approval(self, trip):
        response = trip.post("/api/plan", json={"message": "Plan a trip to Rome"})

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _events(response)
        assert _kinds(events)[0] == "thread"
        assert _kinds(events)[-3:] == ["plan", "approval_required", "done"]
        progress = _nodes(events)
        assert sorted(progress) == sorted(PLANNING_NODES)  # every agent exactly once
        assert progress[0] == "supervisor" and progress[-1] == "itinerary"
        assert "human_approval" not in progress and "final_response" not in progress

        plan = _one(events, "plan")["plan"]
        assert plan["status"] == "awaiting_approval"
        assert plan["summary"] == "Draft plan ready for your review."
        assert plan["trip"]["destination"] == "Rome"
        assert plan["budget"]["categories"]["flights"] == 600.0  # 2 travellers x 300
        assert plan["flights"]["source"] == "mock"
        assert plan["hotels"]["hotels"] == [{"name": "Hotel Test"}]
        assert plan["weather"]["location"] == "Rome, Italy"
        assert len(plan["itinerary"]["itinerary"]) == 3
        assert plan["approval"]["approved"] is None
        request = _one(events, "approval_required")["request"]
        assert request["kind"] == "plan_approval"
        assert request["revision"] == 0 and request["max_revisions"] == settings.mcp.max_revisions

    def test_the_draft_is_stored_and_served_by_the_thread_endpoint(self, trip):
        events = _plan(trip)
        thread_id = _one(events, "thread")["thread_id"]

        body = trip.get(f"/api/threads/{thread_id}").json()

        assert body["plan"] == _one(events, "plan")["plan"]
        assert [m["role"] for m in body["history"]] == ["user", "assistant"]
        assert body["history"][0]["content"] == "Plan a trip to Rome"
        assert (
            body["history"][1]["content"] == "Draft: Trip plan for Rome, 2099-05-10 to 2099-05-12."
        )
        assert body["approval"] is None

    def test_the_paused_run_is_stored_in_the_postgres_checkpointer(self, trip, paused):
        row = trip.portal.call(
            db_pool.execute_one,
            "SELECT count(*) FROM checkpoints WHERE thread_id = %s",
            (paused,),
        )

        assert row[0] > 0

    def test_a_new_message_on_a_paused_thread_starts_a_fresh_request(self, trip, paused):
        second = _plan(trip, "Cheaper please", thread_id=paused)

        assert _one(second, "thread") == {"type": "thread", "thread_id": paused}
        assert _kinds(second)[-3:] == ["plan", "approval_required", "done"]
        body = trip.get(f"/api/threads/{paused}").json()
        assert [m["role"] for m in body["history"]] == ["user", "assistant", "user", "assistant"]
        assert body["plan"] == _one(second, "plan")["plan"]
        assert body["plan"]["approval"]["revision"] == 0

    def test_a_rejected_request_is_streamed_and_stored_as_a_rejected_plan(
        self, client, monkeypatch
    ):
        async def reject(state):
            return {"allowed": False, "reason": "Not a travel request", "selected_agents": []}

        monkeypatch.setattr(graph_module, "supervisor_agent", reject)
        _rebuild_graph()

        events = _plan(client, "write me a poem")

        assert _kinds(events)[-2:] == ["plan", "done"]
        assert "approval_required" not in _kinds(events)
        plan = _one(events, "plan")["plan"]
        assert plan["status"] == "rejected"
        assert plan["reason"] == "Not a travel request"
        assert plan["approval"] is None
        stored = client.get(f"/api/threads/{_one(events, 'thread')['thread_id']}").json()
        assert stored["plan"] == plan

    def test_a_failing_run_streams_a_generic_error_and_stores_no_plan(self, client, monkeypatch):
        async def explode(state):
            raise RuntimeError("401 Incorrect API key provided: sk-live-123")

        monkeypatch.setattr(graph_module, "supervisor_agent", explode)
        _rebuild_graph()

        response = client.post("/api/plan", json={"message": "Plan a trip to Rome"})
        events = _events(response)

        assert events[0]["type"] == "thread"
        assert events[-1] == {"type": "error", "error": PLANNING_FAILED}
        assert "sk-live-123" not in response.text and "RuntimeError" not in response.text
        assert not any(e["type"] in ("plan", "approval_required", "done") for e in events)
        assert client.get(f"/api/threads/{events[0]['thread_id']}").json()["plan"] is None


class TestApproval:
    def test_approving_resumes_the_paused_run_and_finishes_the_plan(self, trip, paused):
        draft = trip.get(f"/api/threads/{paused}").json()["plan"]

        response = _decide(trip, paused, True)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _events(response)
        assert _kinds(events) == ["thread", "progress", "progress", "plan", "done"]
        assert _nodes(events) == ["human_approval", "final_response"]
        plan = _one(events, "plan")["plan"]
        assert plan["status"] == "approved"
        assert plan["approval"]["approved"] is True
        assert plan["summary"] != draft["summary"]
        assert plan["itinerary"] == draft["itinerary"]  # nothing was planned again
        body = trip.get(f"/api/threads/{paused}").json()
        assert body["plan"] == plan
        assert body["approval"] == {"approved": True, "feedback": ""}
        assert [m["role"] for m in body["history"]] == [
            "user",
            "assistant",
            "human_approval",
            "assistant",
        ]
        assert body["history"][2]["metadata"] == {
            "kind": "approval",
            "approved": True,
            "feedback": "",
        }

    def test_a_paused_trip_survives_an_application_restart(self, fake_trip):
        """The checkpoint lives in Postgres, so a new process can finish a trip an old one began."""
        with TestClient(create_app()) as first:
            _rebuild_graph()
            thread_id = _one(_plan(first), "thread")["thread_id"]

        with TestClient(create_app()) as second:
            _rebuild_graph()
            assert second.get(f"/api/threads/{thread_id}").json()["plan"]["status"] == (
                "awaiting_approval"
            )
            events = _events(_decide(second, thread_id, True))

            assert _one(events, "plan")["plan"]["status"] == "approved"

    def test_a_rejection_revises_the_itinerary_and_asks_again(self, trip, paused):
        response = _decide(trip, paused, False, "more food please")

        events = _events(response)
        assert _nodes(events) == ["human_approval", "revise", "itinerary"]
        assert _kinds(events)[-3:] == ["plan", "approval_required", "done"]
        plan = _one(events, "plan")["plan"]
        assert plan["status"] == "awaiting_approval"
        assert plan["approval"]["revision"] == 1
        assert plan["approval"]["feedback_applied"] is True
        assert plan["approval"]["revision_note"] == "Revised."
        assert _one(events, "approval_required")["request"]["revision"] == 1
        assert plan["itinerary"]["itinerary"][0]["activities"] == ["a food tour"]
        # The rejection answered the first draft; the revised draft is still open
        assert trip.get(f"/api/threads/{paused}").json()["approval"] is None
        history = trip.get(f"/api/threads/{paused}").json()["history"]
        assert history[2]["metadata"] == {
            "kind": "approval",
            "approved": False,
            "feedback": "more food please",
        }

    def test_the_revised_draft_can_be_approved(self, trip, paused):
        _decide(trip, paused, False, "more food please")

        events = _events(_decide(trip, paused, True))

        plan = _one(events, "plan")["plan"]
        assert plan["status"] == "approved"
        assert plan["approval"]["revision"] == 1
        assert plan["itinerary"]["itinerary"][0]["activities"] == ["a food tour"]
        assert trip.get(f"/api/threads/{paused}").json()["approval"] == {
            "approved": True,
            "feedback": "",
        }

    def test_the_revision_cap_ends_the_loop_without_an_approval(self, trip, paused, monkeypatch):
        monkeypatch.setattr(settings.mcp, "max_revisions", 1)
        _decide(trip, paused, False, "one")

        events = _events(_decide(trip, paused, False, "two"))

        assert "approval_required" not in _kinds(events)
        assert _kinds(events)[-2:] == ["plan", "done"]
        assert _nodes(events) == ["human_approval", "final_response"]
        plan = _one(events, "plan")["plan"]
        assert plan["status"] == "revision_limit"
        assert plan["approval"]["approved"] is False
        assert trip.get(f"/api/threads/{paused}").json()["approval"] == {
            "approved": False,
            "feedback": "two",
        }

    def test_a_decision_does_not_carry_over_to_a_new_request(self, trip, paused):
        _decide(trip, paused, True)
        assert trip.get(f"/api/threads/{paused}").json()["approval"]["approved"] is True

        again = _plan(trip, "Cheaper", thread_id=paused)

        assert _one(again, "plan")["plan"]["status"] == "awaiting_approval"
        assert trip.get(f"/api/threads/{paused}").json()["approval"] is None
        assert _decide(trip, paused, True).status_code == 200
        assert trip.get(f"/api/threads/{paused}").json()["approval"] == {
            "approved": True,
            "feedback": "",
        }
