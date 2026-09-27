"""JSON-only request bodies (spec v1.1 §11, §12.7 CSRF step 3): other media types get 415."""

from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from ticketward.api.middleware.content_type import JsonBodyMiddleware, is_json_media_type
from ticketward.core.config import Settings
from ticketward.main import create_app
from ticketward.schemas.problem import PROBLEM_MEDIA_TYPE


async def _echo(request: Request) -> dict[str, int]:
    return {"received": len(await request.body())}


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    router = APIRouter(prefix="/api/v1/_test")
    router.add_api_route("/echo", _echo, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    application.include_router(router)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain;charset=UTF-8",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/xml",
        "application/jsonx",
        "application/problem+json",
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_non_json_bodies_on_unsafe_methods_get_415(
    client: TestClient, method: str, content_type: str
) -> None:
    response = client.request(
        method, "/api/v1/_test/echo", content=b"a=1", headers={"content-type": content_type}
    )
    assert response.status_code == 415
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert body["type"] == "/problems/unsupported-media-type"
    assert body["request_id"] == response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_body_without_content_type_gets_415(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo", content=b'{"a": 1}')
    assert response.status_code == 415


@pytest.mark.parametrize(
    "content_type", ["application/json", "Application/JSON; charset=utf-8", " application/json "]
)
def test_json_bodies_are_accepted(client: TestClient, content_type: str) -> None:
    response = client.post(
        "/api/v1/_test/echo", content=b'{"a": 1}', headers={"content-type": content_type}
    )
    assert response.status_code == 200


def test_bodiless_unsafe_requests_are_not_checked(client: TestClient) -> None:
    response = client.post("/api/v1/_test/echo")
    assert response.status_code == 200
    assert response.json() == {"received": 0}


def test_safe_methods_are_not_checked(client: TestClient) -> None:
    response = client.request(
        "GET", "/api/v1/_test/echo", content=b"x", headers={"content-type": "text/plain"}
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("application/json", True),
        ("application/json;charset=utf-8", True),
        ("APPLICATION/JSON", True),
        ("application/json-seq", False),
        ("text/json", False),
    ],
)
def test_is_json_media_type(value: str | None, expected: bool) -> None:
    assert is_json_media_type(value) is expected


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[Message] = []

    async def receive(self) -> Message:
        return {"type": "http.request", "body": b"a=1", "more_body": False}

    async def send(self, message: Message) -> None:
        self.sent.append(message)


async def _never_called(scope: Scope, receive: Receive, send: Send) -> None:
    raise AssertionError


async def test_chunked_non_json_body_gets_415() -> None:
    recorder = _Recorder()
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/raw",
        "headers": [(b"transfer-encoding", b"chunked"), (b"content-type", b"text/plain")],
    }
    await JsonBodyMiddleware(_never_called)(scope, recorder.receive, recorder.send)
    assert recorder.sent[0]["status"] == 415


async def test_malformed_content_length_counts_as_a_body() -> None:
    recorder = _Recorder()
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/raw",
        "headers": [(b"content-length", b"abc"), (b"content-type", b"text/plain")],
    }
    await JsonBodyMiddleware(_never_called)(scope, recorder.receive, recorder.send)
    assert recorder.sent[0]["status"] == 415


async def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    recorder = _Recorder()
    await JsonBodyMiddleware(downstream)({"type": "lifespan"}, recorder.receive, recorder.send)
    assert seen == ["lifespan"]
