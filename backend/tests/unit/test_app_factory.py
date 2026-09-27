from collections.abc import Callable

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from ticketward import __version__
from ticketward.core.config import Environment, Settings
from ticketward.main import DOCS_URL, OPENAPI_URL, TicketwardAPI, _operation_id, create_app


def test_create_app_loads_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TW_ENV", "test")
    monkeypatch.setenv("TW_BODY_LIMIT_DEFAULT_BYTES", "4096")
    app = create_app()
    assert isinstance(app, TicketwardAPI)
    assert app.state.settings.env is Environment.test
    assert app.state.settings.body_limit_default_bytes == 4096
    assert app.version == __version__


def test_non_prod_serves_docs(settings: Settings) -> None:
    app = create_app(settings)
    assert (app.openapi_url, app.docs_url, app.redoc_url) == (OPENAPI_URL, DOCS_URL, None)


def test_docs_can_be_disabled_outside_prod(settings_factory: Callable[..., Settings]) -> None:
    app = create_app(settings_factory(docs_enabled=False))
    assert app.openapi_url is None
    assert app.docs_url is None


def test_openapi_is_built_once(settings: Settings) -> None:
    app = create_app(settings)
    first = app.openapi()
    assert app.openapi() is first


def test_operation_ids_are_tag_prefixed(settings: Settings) -> None:
    app = create_app(settings)
    operation_ids = {
        context.path: context.unique_id
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
    }
    assert operation_ids["/api/v1/health/live"] == "health_live"
    assert operation_ids["/api/v1/health/ready"] == "health_ready"


def test_routers_declare_their_full_prefix(settings: Settings) -> None:
    # scope["route"] exposes the router-local template; logs/metrics need the full one.
    app = create_app(settings)
    contexts = [
        context
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
    ]
    assert contexts
    for context in contexts:
        original = context.original_route
        assert isinstance(original, APIRoute)
        assert context.path == original.path


def test_operation_id_without_tags() -> None:
    async def untagged() -> None:
        return None

    route = APIRoute("/x", untagged, methods=["GET"])
    assert _operation_id(route) == "untagged"


def test_cors_is_off_by_default(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/api/v1/health/live",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
    assert "access-control-allow-origin" not in response.headers


def test_cors_allow_list_is_enforced(settings_factory: Callable[..., Settings]) -> None:
    app = create_app(settings_factory(cors_origins=["http://localhost:3000"]))
    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/health/live",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        denied = client.options(
            "/api/v1/health/live",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in denied.headers
