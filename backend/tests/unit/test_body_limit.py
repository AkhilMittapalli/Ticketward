"""Per-route body limits (spec v1.1 §11, A-25(g)): 413 problem+json above each limit."""

import json
import re
from collections.abc import Callable, Iterator

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.types import Message, Receive, Scope, Send

from ticketward.api.middleware.body_limit import (
    BodyLimitMiddleware,
    BodyLimitRule,
    PayloadTooLargeError,
    body_limit_rules,
)
from ticketward.core.config import MAX_BODY_LIMIT_BYTES, Settings
from ticketward.main import create_app
from ticketward.schemas.problem import PROBLEM_MEDIA_TYPE

KIB = 1024
LIMIT = 2 * KIB  # small default for the generic tests
JSON = {"content-type": "application/json"}


@pytest.fixture
def settings(settings_factory: Callable[..., Settings]) -> Settings:
    return settings_factory(body_limit_default_bytes=LIMIT)


async def _echo(request: Request) -> dict[str, int]:
    return {"received": len(await request.body())}


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    router = APIRouter(prefix="/api/v1/_test")
    router.add_api_route("/echo", _echo, methods=["POST"])
    application.include_router(router)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def routed_client(settings_factory: Callable[..., Settings]) -> Iterator[TestClient]:
    """App with the real default limits and stand-in routes for the named paths."""
    application = create_app(settings_factory())
    router = APIRouter(prefix="/api/v1")
    for path in (
        "/tickets",
        "/tickets/batch",
        "/kb/documents",
        "/kb/documents/{doc_key}/versions",
        "/kb/documents/{doc_key}/versions/{version}/approve",
        "/feedback",
    ):
        router.add_api_route(path, _echo, methods=["POST"])
    router.add_api_route("/drafts/{draft_id}", _echo, methods=["PUT"])
    application.include_router(router)
    with TestClient(application) as test_client:
        yield test_client


def test_body_within_limit_is_accepted(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", content=b"x" * LIMIT, headers=JSON)
    assert response.status_code == 200
    assert response.json() == {"received": LIMIT}


def test_declared_oversize_body_is_rejected_before_the_app(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", content=b"x" * (LIMIT + 1), headers=JSON)
    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.headers["connection"] == "close"
    body = response.json()
    assert body["code"] == "PAYLOAD_TOO_LARGE"
    assert body["type"] == "/problems/payload-too-large"
    assert body["detail"] == f"The request body exceeds the {LIMIT}-byte limit."
    assert body["request_id"] == response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_streamed_oversize_body_is_rejected(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(8):
            yield b"y" * 512

    response = client.post("/api/v1/_test/echo", content=chunks(), headers=JSON)
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.parametrize(
    ("method", "path", "limit"),
    [
        ("POST", "/api/v1/tickets", 256 * KIB),
        ("POST", "/api/v1/tickets/batch", 2048 * KIB),
        ("POST", "/api/v1/kb/documents", 1024 * KIB),
        ("POST", "/api/v1/kb/documents/kb_sso_redirect_loop/versions", 1024 * KIB),
        ("POST", "/api/v1/kb/documents/kb_sso_redirect_loop/versions/3/approve", 64 * KIB),
        ("POST", "/api/v1/feedback", 64 * KIB),
        ("PUT", "/api/v1/drafts/0b7f4f6e", 64 * KIB),
    ],
)
def test_each_route_gets_its_spec_limit(
    routed_client: TestClient, method: str, path: str, limit: int
) -> None:
    at_limit = routed_client.request(method, path, content=b"x" * limit, headers=JSON)
    assert at_limit.status_code == 200
    assert at_limit.json() == {"received": limit}
    over = routed_client.request(method, path, content=b"x" * (limit + 1), headers=JSON)
    assert over.status_code == 413
    assert over.json()["detail"] == f"The request body exceeds the {limit}-byte limit."


def test_streamed_ticket_body_uses_the_ticket_limit(routed_client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(9):
            yield b"z" * (32 * KIB)  # 288 KiB in total, above 256 KiB

    response = routed_client.post("/api/v1/tickets", content=chunks(), headers=JSON)
    assert response.status_code == 413
    assert response.json()["detail"] == f"The request body exceeds the {256 * KIB}-byte limit."


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/v1/tickets", "ticket"),
        ("POST", "/api/v1/tickets/", "ticket"),
        ("POST", "/api/v1/tickets/batch", "ticket_batch"),
        ("POST", "/api/v1/kb/documents", "kb_document"),
        ("POST", "/api/v1/kb/documents/kb_x/versions", "kb_document_version"),
        ("GET", "/api/v1/tickets", None),
        ("POST", "/api/v1/tickets-archive", None),
        ("POST", "/api/v1/tickets/0b7f4f6e/reprocess", None),
        ("POST", "/api/v1/kb/documents/a/b/versions", None),
        ("POST", "/api/v2/tickets", None),
    ],
)
def test_rule_resolution(
    settings_factory: Callable[..., Settings], method: str, path: str, expected: str | None
) -> None:
    rules = body_limit_rules(settings_factory())
    matched = [rule.name for rule in rules if rule.matches(method, path)]
    assert matched == ([expected] if expected else [])


def test_limits_come_from_settings(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(
        body_limit_default_bytes=4 * KIB,
        body_limit_ticket_bytes=8 * KIB,
        body_limit_ticket_batch_bytes=16 * KIB,
        body_limit_kb_document_bytes=12 * KIB,
    )
    middleware = BodyLimitMiddleware(
        _never_called, settings.body_limit_default_bytes, body_limit_rules(settings)
    )
    assert middleware.limit_for("POST", "/api/v1/tickets") == 8 * KIB
    assert middleware.limit_for("POST", "/api/v1/tickets/batch") == 16 * KIB
    assert middleware.limit_for("POST", "/api/v1/kb/documents") == 12 * KIB
    assert middleware.limit_for("POST", "/api/v1/queues") == 4 * KIB


def test_spec_default_limits(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory()
    assert settings.body_limit_default_bytes == 64 * KIB
    assert settings.body_limit_ticket_bytes == 256 * KIB
    assert settings.body_limit_ticket_batch_bytes == 2 * KIB * KIB
    assert settings.body_limit_kb_document_bytes == KIB * KIB


@pytest.mark.parametrize("value", [512, MAX_BODY_LIMIT_BYTES + 1])
def test_limits_are_bounded_below_the_edge_cap(
    settings_factory: Callable[..., Settings], value: int
) -> None:
    with pytest.raises(ValidationError):
        settings_factory(body_limit_ticket_batch_bytes=value)


class _Recorder:
    def __init__(self, body_chunks: list[bytes]) -> None:
        self.body_chunks = list(body_chunks)
        self.sent: list[Message] = []

    async def receive(self) -> Message:
        if self.body_chunks:
            chunk = self.body_chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(self.body_chunks)}
        return {"type": "http.disconnect"}

    async def send(self, message: Message) -> None:
        self.sent.append(message)

    @property
    def status(self) -> int:
        return int(self.sent[0]["status"])

    @property
    def json_body(self) -> dict[str, object]:
        body = b"".join(message.get("body", b"") for message in self.sent[1:])
        decoded: dict[str, object] = json.loads(body)
        return decoded


def _scope(headers: list[tuple[bytes, bytes]], path: str = "/api/v1/raw") -> Scope:
    return {"type": "http", "method": "POST", "path": path, "headers": headers}


async def _read_all(receive: Receive) -> bytes:
    body = b""
    while True:
        message = await receive()
        chunk: bytes = message.get("body", b"")
        body += chunk
        if not message.get("more_body"):
            return body


async def _never_called(scope: Scope, receive: Receive, send: Send) -> None:
    raise AssertionError


@pytest.mark.parametrize("value", [b"abc", b"-5"])
async def test_invalid_content_length_is_bad_request(value: bytes) -> None:
    recorder = _Recorder([])
    middleware = BodyLimitMiddleware(_never_called, default_limit_bytes=LIMIT)
    await middleware(_scope([(b"content-length", value)]), recorder.receive, recorder.send)
    assert recorder.status == 400
    assert recorder.json_body["code"] == "BAD_REQUEST"


async def test_rule_limit_applies_to_streamed_bodies() -> None:
    async def raw_app(scope: Scope, receive: Receive, send: Send) -> None:
        await _read_all(receive)
        raise AssertionError  # unreachable: the body is too large

    rule = BodyLimitRule("ticket", "POST", re.compile(r"/api/v1/tickets"), 1000)
    recorder = _Recorder([b"z" * 600, b"z" * 600])
    await BodyLimitMiddleware(raw_app, default_limit_bytes=LIMIT, rules=[rule])(
        _scope([], path="/api/v1/tickets"), recorder.receive, recorder.send
    )
    assert recorder.status == 413
    assert recorder.json_body["detail"] == "The request body exceeds the 1000-byte limit."


async def test_limit_enforced_for_apps_that_do_not_handle_the_error() -> None:
    async def raw_app(scope: Scope, receive: Receive, send: Send) -> None:
        await _read_all(receive)
        raise AssertionError  # unreachable: the body is too large

    recorder = _Recorder([b"z" * 1500, b"z" * 1500])
    await BodyLimitMiddleware(raw_app, default_limit_bytes=LIMIT)(
        _scope([]), recorder.receive, recorder.send
    )
    assert recorder.status == 413
    assert recorder.json_body["code"] == "PAYLOAD_TOO_LARGE"


async def test_non_body_messages_pass_through_the_limiter() -> None:
    received: list[str] = []

    async def app_waiting_for_disconnect(scope: Scope, receive: Receive, send: Send) -> None:
        await _read_all(receive)
        received.append((await receive())["type"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    recorder = _Recorder([b"small"])
    await BodyLimitMiddleware(app_waiting_for_disconnect, default_limit_bytes=LIMIT)(
        _scope([]), recorder.receive, recorder.send
    )
    assert received == ["http.disconnect"]
    assert recorder.status == 204


async def test_limit_error_after_response_start_propagates() -> None:
    async def eager_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await _read_all(receive)

    recorder = _Recorder([b"z" * 1500, b"z" * 1500])
    with pytest.raises(PayloadTooLargeError):
        await BodyLimitMiddleware(eager_app, default_limit_bytes=LIMIT)(
            _scope([]), recorder.receive, recorder.send
        )


async def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    recorder = _Recorder([])
    await BodyLimitMiddleware(downstream, default_limit_bytes=LIMIT)(
        {"type": "websocket"}, recorder.receive, recorder.send
    )
    assert seen == ["websocket"]
