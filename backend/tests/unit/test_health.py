from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.testing import capture_logs

from ticketward.core.config import Settings
from ticketward.core.redis import create_redis_client
from ticketward.db.session import create_db_engine
from ticketward.main import create_app
from ticketward.services.health import (
    CheckOutcome,
    DatabaseHealthCheck,
    HealthCheck,
    RedisHealthCheck,
    run_checks,
)

type Factory = Callable[..., HealthCheck]
type Override = Callable[[FastAPI, list[HealthCheck]], None]


def test_live_needs_no_dependencies(app: FastAPI) -> None:
    # No lifespan (no context manager): liveness must not depend on startup state.
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_ok_with_healthy_checks(
    client: TestClient, app: FastAPI, check_factory: Factory, override_checks: Override
) -> None:
    override_checks(app, [check_factory("db"), check_factory("redis")])
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"db": "ok", "redis": "ok"}}


def test_ready_failure_is_generic_503_problem(
    client: TestClient, app: FastAPI, check_factory: Factory, override_checks: Override
) -> None:
    override_checks(app, [check_factory("db", ok=False), check_factory("redis")])
    with capture_logs() as logs:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "UPSTREAM_UNAVAILABLE"
    assert body["detail"] == "One or more dependencies are unavailable."
    for leaked in ("10.0.0.5", "hunter2", "ConnectionRefusedError", "db"):
        assert leaked not in response.text
    failures = [entry for entry in logs if entry["event"] == "health.check_failed"]
    assert failures == [
        {
            "event": "health.check_failed",
            "component": "db",
            "error_type": "ConnectionRefusedError",
            "log_level": "warning",
        }
    ]


def test_ready_times_out_slow_checks(
    settings_factory: Callable[..., Settings], check_factory: Factory, override_checks: Override
) -> None:
    application = create_app(settings_factory(ready_check_timeout_s=0.05))
    override_checks(application, [check_factory("db", delay_s=1.0)])
    with TestClient(application) as test_client:
        response = test_client.get("/api/v1/health/ready")
    assert response.status_code == 503


def test_ready_fails_closed_without_registered_checks(app: FastAPI) -> None:
    response = TestClient(app).get("/api/v1/health/ready")  # lifespan not run
    assert response.status_code == 503
    assert response.json()["code"] == "UPSTREAM_UNAVAILABLE"


async def test_run_checks_preserves_order_and_isolates_failures(check_factory: Factory) -> None:
    checks = [check_factory("a"), check_factory("b", ok=False), check_factory("c")]
    outcomes = await run_checks(checks, timeout_s=1.0)
    assert outcomes == [
        CheckOutcome("a", ok=True),
        CheckOutcome("b", ok=False),
        CheckOutcome("c", ok=True),
    ]


class _FakeConnection:
    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.statements: list[str] = []

    async def execute(self, statement: Any) -> None:
        if self.fail:
            msg = "db down"
            raise OSError(msg)
        self.statements.append(str(statement))


class _FakeEngine:
    def __init__(self, fail: bool = False) -> None:
        self.connection = _FakeConnection(fail)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[_FakeConnection]:
        yield self.connection


async def test_database_check_runs_select_one() -> None:
    engine = _FakeEngine()
    check = DatabaseHealthCheck(cast(AsyncEngine, engine))
    await check.check()
    assert check.name == "db"
    assert engine.connection.statements == ["SELECT 1"]


async def test_database_check_propagates_failures() -> None:
    check = DatabaseHealthCheck(cast(AsyncEngine, _FakeEngine(fail=True)))
    with pytest.raises(OSError, match="db down"):
        await check.check()


class _SyncPing:
    def __init__(self, reply: bool) -> None:
        self.reply = reply

    def ping(self) -> bool:
        return self.reply


class _AsyncPing:
    def ping(self) -> Awaitable[bool]:
        async def reply() -> bool:
            return True

        return reply()


async def test_redis_check_accepts_sync_and_async_clients() -> None:
    await RedisHealthCheck(_AsyncPing()).check()
    await RedisHealthCheck(_SyncPing(reply=True)).check()
    assert RedisHealthCheck(_SyncPing(reply=True)).name == "redis"


async def test_redis_check_rejects_falsy_reply() -> None:
    with pytest.raises(ConnectionError, match="falsy"):
        await RedisHealthCheck(_SyncPing(reply=False)).check()


async def test_real_clients_report_unreachable_services(
    settings_factory: Callable[..., Settings],
) -> None:
    # Port 9 (discard) on loopback is closed on CI and dev machines: fast refusal.
    settings = settings_factory(
        db_host="127.0.0.1",
        db_port=9,
        db_connect_timeout_s=2.0,
        redis_url="redis://127.0.0.1:9/0",
        redis_socket_timeout_s=1.0,
    )
    engine = create_db_engine(settings)
    redis = create_redis_client(settings)
    try:
        outcomes = await run_checks(
            [DatabaseHealthCheck(engine), RedisHealthCheck(redis)], timeout_s=3.0
        )
    finally:
        await redis.aclose()
        await engine.dispose()
    assert outcomes == [CheckOutcome("db", ok=False), CheckOutcome("redis", ok=False)]


def test_lifespan_registers_and_releases_clients(app: FastAPI) -> None:
    with TestClient(app):
        checks = app.state.readiness_checks
        assert [check.name for check in checks] == ["db", "redis"]
        assert isinstance(app.state.db_engine, AsyncEngine)
        assert app.state.session_factory is not None
