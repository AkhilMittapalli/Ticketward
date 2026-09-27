import re
import time
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from ticketward.api.middleware.request_id import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    current_request_id,
    is_valid_request_id,
    new_request_id,
)
from ticketward.core.config import Settings
from ticketward.main import create_app

ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    router = APIRouter(prefix="/api/v1/_test")

    @router.get("/request-id")
    async def echo_request_id() -> dict[str, str | None]:
        return {"request_id": current_request_id()}

    application.include_router(router)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_new_request_id_is_a_ulid() -> None:
    first = new_request_id()
    time.sleep(0.002)
    second = new_request_id()
    assert ULID_RE.fullmatch(first)
    assert ULID_RE.fullmatch(second)
    assert first[:10] <= second[:10]  # 48-bit millisecond timestamp prefix sorts by time
    assert first != second


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("01J8ZB4Q2X7N5M3K1H9G6F4D2C", True),
        ("3f2b8c1e-1234-4567-8901-123456789012", True),
        ("req-test-0001", True),
        ("trace:abc.def_123", True),
        ("short", False),
        ("-starts-with-dash", False),
        ("has space inside", False),
        ("x" * 129, False),
        ("inject\nnewline", False),
    ],
)
def test_request_id_validation(value: str, valid: bool) -> None:
    assert is_valid_request_id(value) is valid


def test_request_id_generated_when_absent(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert ULID_RE.fullmatch(response.headers[REQUEST_ID_HEADER])


def test_valid_incoming_request_id_is_echoed_and_visible_in_handlers(client: TestClient) -> None:
    response = client.get("/api/v1/_test/request-id", headers={REQUEST_ID_HEADER: "req-abc-123456"})
    assert response.headers[REQUEST_ID_HEADER] == "req-abc-123456"
    assert response.json() == {"request_id": "req-abc-123456"}


def test_invalid_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={REQUEST_ID_HEADER: "bad id!"})
    assert ULID_RE.fullmatch(response.headers[REQUEST_ID_HEADER])


def test_request_id_context_is_cleared_after_request(client: TestClient) -> None:
    client.get("/api/v1/health/live")
    assert current_request_id() is None


def test_access_log_line_uses_route_template(client: TestClient) -> None:
    with capture_logs(processors=[merge_contextvars]) as logs:
        response = client.get(
            "/api/v1/_test/request-id", headers={REQUEST_ID_HEADER: "req-log-00001"}
        )
    entries = [entry for entry in logs if entry["event"] == "http.request"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["route"] == "/api/v1/_test/request-id"
    assert entry["method"] == "GET"
    assert entry["status"] == response.status_code == 200
    assert entry["request_id"] == "req-log-00001"
    assert entry["latency_ms"] >= 0
    assert entry["log_level"] == "info"


def test_health_and_unmatched_requests_are_logged_quietly_or_by_path(client: TestClient) -> None:
    with capture_logs() as logs:
        client.get("/api/v1/health/live")
        client.get("/api/v1/unknown/alice@example.com")
    health, unmatched = (entry for entry in logs if entry["event"] == "http.request")
    assert health["log_level"] == "debug"
    assert "path" in unmatched
    assert "route" not in unmatched
    assert unmatched["status"] == 404


async def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        return None

    await RequestIdMiddleware(downstream)({"type": "lifespan"}, receive, send)
    assert seen == ["lifespan"]
