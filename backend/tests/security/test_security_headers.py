from collections.abc import Callable, Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx import Headers
from starlette.types import Message, Receive, Scope, Send

from ticketward.api.middleware.security_headers import (
    API_CSP,
    BASE_SECURITY_HEADERS,
    DOCS_CSP,
    SecurityHeadersMiddleware,
)
from ticketward.core.config import Settings
from ticketward.main import DOCS_URL, OPENAPI_URL, create_app


@pytest.fixture
def app(settings_factory: Callable[..., Settings]) -> FastAPI:
    application = create_app(settings_factory(body_limit_default_bytes=1024))
    router = APIRouter(prefix="/api/v1/_test")

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    @router.post("/echo")
    async def echo(payload: dict[str, str]) -> dict[str, str]:
        return payload

    @router.get("/cacheable")
    async def cacheable() -> JSONResponse:
        return JSONResponse({"ok": True}, headers={"Cache-Control": "private, max-age=60"})

    application.include_router(router)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _assert_hardened(headers: Headers, csp: str = API_CSP) -> None:
    for name, value in BASE_SECURITY_HEADERS:
        assert headers.get(name) == value, name
    assert headers.get("content-security-policy") == csp


@pytest.mark.parametrize(
    ("method", "path", "body", "status"),
    [
        ("GET", "/api/v1/health/live", None, 200),
        ("GET", "/api/v1/does-not-exist", None, 404),
        ("POST", "/api/v1/_test/echo", b'{"a": 1}', 422),
        ("POST", "/api/v1/_test/echo", b"x" * 2048, 413),
        ("GET", "/api/v1/_test/boom", None, 500),
    ],
)
def test_every_api_response_is_hardened(
    client: TestClient, method: str, path: str, body: bytes | None, status: int
) -> None:
    response = client.request(
        method, path, content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == status
    _assert_hardened(response.headers)
    assert response.headers["cache-control"] == "no-store"


def test_route_may_override_cache_control(client: TestClient) -> None:
    response = client.get("/api/v1/_test/cacheable")
    assert response.headers["cache-control"] == "private, max-age=60"
    _assert_hardened(response.headers)


def test_non_api_paths_get_headers_without_no_store(client: TestClient) -> None:
    response = client.get("/favicon.ico")
    assert response.status_code == 404
    _assert_hardened(response.headers)
    assert "cache-control" not in response.headers


def test_swagger_ui_gets_docs_scoped_csp(client: TestClient) -> None:
    response = client.get(DOCS_URL)
    assert response.status_code == 200
    _assert_hardened(response.headers, csp=DOCS_CSP)
    openapi = client.get(OPENAPI_URL)
    assert openapi.status_code == 200
    assert openapi.headers["content-security-policy"] == API_CSP


def test_api_csp_is_locked_down() -> None:
    assert "default-src 'none'" in API_CSP
    assert "frame-ancestors 'none'" in API_CSP
    assert "unsafe" not in API_CSP


async def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        return None

    await SecurityHeadersMiddleware(downstream)({"type": "lifespan"}, receive, send)
    assert seen == ["lifespan"]
