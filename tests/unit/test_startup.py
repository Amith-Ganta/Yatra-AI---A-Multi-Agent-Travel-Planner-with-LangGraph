"""Startup (F0): the app must open the DB pool, run migrations and then bring up the agent runtime.

The order matters: the LangGraph saver creates its own tables, so it has to come after the
migrations that drop the legacy ``checkpoints`` table, and the graph needs the saver.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.core.startup as startup


@pytest.fixture
def no_sleep(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(startup.asyncio, "sleep", sleep)
    return sleep


@pytest.fixture
def stubs(monkeypatch):
    """Replace every startup collaborator; ``stubs.order`` records the call order."""
    order: list[str] = []

    def recording(name: str, mock=None):
        mock = mock or AsyncMock()

        async def call(*args, **kwargs):
            order.append(name)
            return await mock(*args, **kwargs)

        call.mock = mock
        return call

    init = recording("db_pool.init")
    migrate = recording("run_migrations")
    saver_init = recording("checkpoint_store.init")
    saver_close = recording("checkpoint_store.close")
    pool_close = recording("db_pool.close")
    start = recording("start_mcp")
    stop = recording("stop_mcp")
    graph = MagicMock(side_effect=lambda saver: order.append("init_graph"))
    close_graph = MagicMock(side_effect=lambda: order.append("close_graph"))

    monkeypatch.setattr(startup.db_pool, "init", init)
    monkeypatch.setattr(startup.db_pool, "close", pool_close)
    monkeypatch.setattr(startup, "run_migrations", migrate)
    monkeypatch.setattr(startup.checkpoint_store, "init", saver_init)
    monkeypatch.setattr(startup.checkpoint_store, "close", saver_close)
    # The real ``init`` is stubbed out, so give the store the saver it would have created.
    monkeypatch.setattr(startup.checkpoint_store, "_saver", object())
    monkeypatch.setattr(startup, "init_graph", graph)
    monkeypatch.setattr(startup, "close_graph", close_graph)
    monkeypatch.setattr(startup, "start_mcp", start)
    monkeypatch.setattr(startup, "stop_mcp", stop)
    monkeypatch.setattr(startup.settings.database, "url", "postgresql://u:p@localhost:5432/db")
    return SimpleNamespace(
        order=order,
        init=init.mock,
        migrate=migrate.mock,
        saver_init=saver_init.mock,
        graph=graph,
        start_mcp=start.mock,
    )


@pytest.mark.asyncio
async def test_init_app_opens_the_pool_then_runs_migrations(stubs, no_sleep):
    await startup.init_app()

    stubs.init.assert_awaited_once()
    stubs.migrate.assert_awaited_once()
    assert startup.db_pool.database_url == "postgresql://u:p@localhost:5432/db"


@pytest.mark.asyncio
async def test_init_app_brings_everything_up_in_dependency_order(stubs, no_sleep):
    await startup.init_app()

    assert stubs.order == [
        "db_pool.init",
        "run_migrations",
        "checkpoint_store.init",
        "init_graph",
        "start_mcp",
    ]
    stubs.saver_init.assert_awaited_once_with("postgresql://u:p@localhost:5432/db")
    stubs.graph.assert_called_once_with(startup.checkpoint_store.saver)


@pytest.mark.asyncio
async def test_init_app_retries_until_the_database_is_up(stubs, no_sleep):
    stubs.init.side_effect = [ConnectionError("starting"), ConnectionError("starting"), None]

    await startup.init_app()

    assert stubs.init.await_count == 3
    assert no_sleep.await_count == 2
    stubs.migrate.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_app_fails_fast_after_the_last_attempt(stubs, no_sleep):
    stubs.init.side_effect = ConnectionError("down")

    with pytest.raises(RuntimeError, match="Could not connect"):
        await startup.init_app()

    assert stubs.init.await_count == startup.DB_CONNECT_ATTEMPTS
    stubs.migrate.assert_not_awaited()
    stubs.saver_init.assert_not_awaited()
    stubs.graph.assert_not_called()
    stubs.start_mcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_final_error_names_the_database_host_but_never_the_credentials(
    stubs, no_sleep, monkeypatch
):
    monkeypatch.setattr(
        startup.settings.database,
        "url",
        "postgresql://amith:s3cret@db.example.com:5432/app?sslmode=require",
    )
    stubs.init.side_effect = ConnectionError("down")

    with pytest.raises(RuntimeError) as exc:
        await startup.init_app()

    message = str(exc.value)
    assert "db.example.com:5432/app" in message
    assert "s3cret" not in message and "amith" not in message and "sslmode" not in message
    assert "private (internal) address" not in message


@pytest.mark.asyncio
async def test_a_private_host_name_gets_the_external_url_hint(stubs, no_sleep, monkeypatch):
    monkeypatch.setattr(
        startup.settings.database, "url", "postgresql://u:p@dpg-abc123-a/agentmemory"
    )
    stubs.init.side_effect = ConnectionError("down")

    with pytest.raises(RuntimeError) as exc:
        await startup.init_app()

    assert "dpg-abc123-a/agentmemory" in str(exc.value)
    assert "external connection string" in str(exc.value)


def test_an_unparseable_url_never_raises_while_describing_the_target():
    assert startup._database_target("postgresql://u:p@db.example.com:notaport/x") == (
        "unparseable DATABASE_URL"
    )
    assert startup._database_target("postgresql://u:p@[broken/x") == "unparseable DATABASE_URL"
    assert startup._connection_hint("postgresql://u:p@[broken/x") == ""


@pytest.mark.asyncio
async def test_init_app_requires_a_database_url(stubs, monkeypatch):
    monkeypatch.setattr(startup.settings.database, "url", None)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        await startup.init_app()

    assert stubs.order == []


@pytest.mark.asyncio
async def test_a_failing_migration_stops_startup_before_the_agent_runtime(stubs, no_sleep):
    stubs.migrate.side_effect = RuntimeError("bad sql")

    with pytest.raises(RuntimeError, match="bad sql"):
        await startup.init_app()

    assert "init_graph" not in stubs.order and "start_mcp" not in stubs.order


@pytest.mark.asyncio
async def test_close_app_shuts_down_in_reverse_order(stubs):
    await startup.close_app()

    assert stubs.order == ["stop_mcp", "close_graph", "checkpoint_store.close", "db_pool.close"]
