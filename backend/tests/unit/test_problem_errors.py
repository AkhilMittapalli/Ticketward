from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from ticketward.api.errors import UnhandledErrorMiddleware, code_for_status
from ticketward.core.config import Settings
from ticketward.domain.errors import (
    ConflictError,
    DemoLockedError,
    DomainError,
    IdempotencyMismatchError,
    MaintenanceError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    RefreshSupersededError,
    UpstreamUnavailableError,
)
from ticketward.main import create_app
from ticketward.schemas.problem import PROBLEM_MEDIA_TYPE, ErrorCode, problem_type_uri
from ticketward.schemas.ticket import TicketCreate

SECRET_TEXT = "password=hunter2 for alice@example.com"


def _test_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/_test")

    @router.post("/tickets")
    async def create_ticket(ticket: TicketCreate) -> dict[str, int]:
        return {"subject_length": len(ticket.subject)}

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError(SECRET_TEXT)

    @router.get("/domain/{kind}")
    async def domain(kind: str) -> None:
        errors: dict[str, DomainError] = {
            "not_found": NotFoundError("Ticket not found."),
            "conflict": ConflictError(),
            "idempotency": IdempotencyMismatchError(),
            "forbidden": PermissionDeniedError(),
            "rate": RateLimitedError(retry_after_s=30),
            "upstream": UpstreamUnavailableError(),
            "demo_locked": DemoLockedError(),
            "refresh_superseded": RefreshSupersededError(),
            "maintenance": MaintenanceError(retry_after_s=120),
            "maintenance_no_retry": MaintenanceError(),
            "base": DomainError(),
        }
        raise errors[kind]

    @router.get("/http/{status_code}")
    async def http_error(status_code: int) -> None:
        raise HTTPException(
            status_code=status_code,
            detail=f"custom detail {SECRET_TEXT}" if status_code >= 500 else "Custom detail.",
            headers={"WWW-Authenticate": 'Cookie realm="rf"'} if status_code == 401 else None,
        )

    return router


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.include_router(_test_router())
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def assert_problem(response: Any, status: int, code: ErrorCode) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body: dict[str, Any] = response.json()
    assert body["status"] == status
    assert body["code"] == code.value
    assert body["type"] == problem_type_uri(code)
    assert body["title"]
    assert body["detail"]
    assert body["request_id"] == response.headers["x-request-id"]
    return body


def test_problem_type_uris_are_relative_and_kebab_case() -> None:
    # A-25(j): relative references, so no owned domain is needed.
    assert problem_type_uri(ErrorCode.VALIDATION_ERROR) == "/problems/validation-error"
    assert problem_type_uri(ErrorCode.UNSUPPORTED_MEDIA_TYPE) == "/problems/unsupported-media-type"
    for code in ErrorCode:
        assert problem_type_uri(code).startswith("/problems/")


def test_error_codes_match_spec_v1_1() -> None:
    assert {code.value for code in ErrorCode} == {
        "BAD_REQUEST",
        "VALIDATION_ERROR",
        "UNAUTHENTICATED",
        "FORBIDDEN",
        "CSRF_FAILED",
        "DEMO_LOCKED",
        "NOT_FOUND",
        "METHOD_NOT_ALLOWED",
        "CONFLICT",
        "REFRESH_SUPERSEDED",
        "IDEMPOTENCY_MISMATCH",
        "PAYLOAD_TOO_LARGE",
        "UNSUPPORTED_MEDIA_TYPE",
        "RATE_LIMITED",
        "UPSTREAM_UNAVAILABLE",
        "MAINTENANCE",
        "INTERNAL",
    }


def test_unknown_route_is_not_found_problem(client: TestClient) -> None:
    body = assert_problem(client.get("/api/v1/nope"), 404, ErrorCode.NOT_FOUND)
    assert body["instance"] == "/api/v1/nope"
    assert body["detail"] == "The requested resource was not found."


def test_wrong_method_is_method_not_allowed_with_allow_header(client: TestClient) -> None:
    response = client.delete("/api/v1/health/live")
    assert_problem(response, 405, ErrorCode.METHOD_NOT_ALLOWED)
    assert response.headers["allow"] == "GET"


def test_validation_error_shape_never_echoes_input(client: TestClient) -> None:
    marker = "UNIQUE-MARKER-" + "x" * 300
    payload = {
        "customer_tier": "business",
        "channel": "web_form",
        "subject": marker,
        "message": "Okta SSO loop",
        "unexpected": "field",
    }
    response = client.post("/api/v1/_test/tickets", json=payload)
    body = assert_problem(response, 422, ErrorCode.VALIDATION_ERROR)
    assert body["title"] == "Request validation failed"
    assert body["detail"] == "One or more fields are invalid."
    assert body["instance"] == "/api/v1/_test/tickets"
    by_loc = {tuple(error["loc"]): error for error in body["errors"]}
    assert by_loc[("body", "subject")]["type"] == "string_too_long"
    assert by_loc[("body", "unexpected")]["type"] == "extra_forbidden"
    for error in body["errors"]:
        assert set(error) == {"loc", "msg", "type"}
    assert "UNIQUE-MARKER" not in response.text


def test_malformed_json_is_validation_problem(client: TestClient) -> None:
    response = client.post(
        "/api/v1/_test/tickets",
        content=b'{"subject": "unterminated',
        headers={"content-type": "application/json"},
    )
    body = assert_problem(response, 422, ErrorCode.VALIDATION_ERROR)
    assert body["errors"][0]["type"] == "json_invalid"
    assert "unterminated" not in response.text


def test_unhandled_exception_is_generic_500_with_request_id(client: TestClient) -> None:
    with capture_logs(processors=[merge_contextvars]) as logs:
        response = client.get("/api/v1/_test/boom", headers={"X-Request-ID": "req-test-0001"})
    body = assert_problem(response, 500, ErrorCode.INTERNAL)
    assert body["request_id"] == "req-test-0001"
    assert "request_id" in body["detail"]
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    events = [entry for entry in logs if entry["event"] == "http.unhandled_exception"]
    assert len(events) == 1
    assert events[0]["request_id"] == "req-test-0001"
    assert events[0]["error_type"] == "RuntimeError"
    assert events[0]["log_level"] == "error"


@pytest.mark.parametrize(
    ("kind", "status", "code", "detail"),
    [
        ("not_found", 404, ErrorCode.NOT_FOUND, "Ticket not found."),
        ("conflict", 409, ErrorCode.CONFLICT, None),
        ("idempotency", 422, ErrorCode.IDEMPOTENCY_MISMATCH, None),
        ("forbidden", 403, ErrorCode.FORBIDDEN, None),
        ("rate", 429, ErrorCode.RATE_LIMITED, None),
        ("upstream", 503, ErrorCode.UPSTREAM_UNAVAILABLE, None),
        ("demo_locked", 403, ErrorCode.DEMO_LOCKED, "This action is disabled in the public demo."),
        ("refresh_superseded", 409, ErrorCode.REFRESH_SUPERSEDED, None),
        ("maintenance", 503, ErrorCode.MAINTENANCE, None),
        ("maintenance_no_retry", 503, ErrorCode.MAINTENANCE, None),
        ("base", 400, ErrorCode.BAD_REQUEST, "The request could not be completed."),
    ],
)
def test_domain_errors_map_to_problem_types(
    client: TestClient, kind: str, status: int, code: ErrorCode, detail: str | None
) -> None:
    response = client.get(f"/api/v1/_test/domain/{kind}")
    body = assert_problem(response, status, code)
    if detail is not None:
        assert body["detail"] == detail
    expected_retry_after = {"rate": "30", "maintenance": "120"}.get(kind)
    assert response.headers.get("retry-after") == expected_retry_after


def test_retry_after_values_are_at_least_one_second() -> None:
    assert RateLimitedError(retry_after_s=0).retry_after_s == 1
    assert MaintenanceError(retry_after_s=0).retry_after_s == 1
    assert MaintenanceError().retry_after_s is None


def test_code_specific_errors_keep_their_generic_parents() -> None:
    # Handlers written for the generic class still catch the specific ones.
    assert isinstance(DemoLockedError(), PermissionDeniedError)
    assert isinstance(RefreshSupersededError(), ConflictError)
    assert isinstance(MaintenanceError(), UpstreamUnavailableError)


def test_http_exception_4xx_detail_and_headers_pass_through(client: TestClient) -> None:
    response = client.get("/api/v1/_test/http/401")
    body = assert_problem(response, 401, ErrorCode.UNAUTHENTICATED)
    assert body["detail"] == "Custom detail."
    assert response.headers["www-authenticate"] == 'Cookie realm="rf"'


def test_http_exception_5xx_detail_is_never_passed_through(client: TestClient) -> None:
    response = client.get("/api/v1/_test/http/502")
    body = assert_problem(response, 502, ErrorCode.UPSTREAM_UNAVAILABLE)
    assert "hunter2" not in response.text
    assert body["detail"] == "A required upstream service is temporarily unavailable."


def test_http_415_maps_to_unsupported_media_type(client: TestClient) -> None:
    assert_problem(client.get("/api/v1/_test/http/415"), 415, ErrorCode.UNSUPPORTED_MEDIA_TYPE)


def test_unmapped_http_status_falls_back_by_class(client: TestClient) -> None:
    assert_problem(client.get("/api/v1/_test/http/418"), 418, ErrorCode.BAD_REQUEST)
    nonstandard = assert_problem(client.get("/api/v1/_test/http/499"), 499, ErrorCode.BAD_REQUEST)
    assert nonstandard["detail"] == "Custom detail."
    assert code_for_status(501) is ErrorCode.INTERNAL
    assert code_for_status(599) is ErrorCode.INTERNAL
    assert code_for_status(451) is ErrorCode.BAD_REQUEST


def test_errors_escaping_the_middleware_stack_get_last_resort_problem(
    settings: Settings,
) -> None:
    application = create_app(settings)

    class ExplodingMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                raise RuntimeError(SECRET_TEXT)
            await self.app(scope, receive, send)

    application.add_middleware(ExplodingMiddleware)
    with (
        capture_logs() as logs,
        TestClient(application, raise_server_exceptions=False) as test_client,
    ):
        response = test_client.get("/api/v1/health/live")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json()["code"] == "INTERNAL"
    assert "hunter2" not in response.text
    assert any(entry["event"] == "http.unhandled_exception" for entry in logs)


async def test_unhandled_error_middleware_reraises_after_response_started() -> None:
    async def streaming_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("mid-stream failure")

    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = UnhandledErrorMiddleware(streaming_app)
    scope: Scope = {"type": "http", "method": "GET", "path": "/stream", "headers": []}
    with pytest.raises(RuntimeError, match="mid-stream failure"):
        await middleware(scope, receive, send)
    assert [message["type"] for message in sent] == ["http.response.start"]
