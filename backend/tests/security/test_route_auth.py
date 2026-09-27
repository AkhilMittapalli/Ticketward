"""Deny-by-default route authorization test (spec §12.2 "Elevation", §12.3 A01).

Every API route must either appear in ``PUBLIC_ROUTES`` or declare a dependency marked
with ``auth_dependency`` somewhere in its effective dependency tree (route, router or
include-level dependencies). P4 adds ``require_roles``; until then only the public
health probes exist.
"""

from collections.abc import Iterator
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from fastapi.testclient import TestClient

from ticketward.api import API_V1_PREFIX
from ticketward.api.deps import AUTH_DEPENDENCY_ATTR, PUBLIC_ROUTES, auth_dependency
from ticketward.core.config import Settings
from ticketward.main import DOCS_URL, OPENAPI_URL, create_app


def api_route_contexts(app: FastAPI) -> list[RouteContext]:
    """Effective API routes, with include-level prefixes and dependencies applied."""
    return [
        context
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
    ]


def _iter_dependants(dependant: Dependant) -> Iterator[Dependant]:
    yield dependant
    for child in dependant.dependencies:
        yield from _iter_dependants(child)


def has_auth_dependency(context: RouteContext) -> bool:
    dependant: Any = context.dependant
    if not isinstance(dependant, Dependant):
        return False
    return any(
        getattr(node.call, AUTH_DEPENDENCY_ATTR, False) for node in _iter_dependants(dependant)
    )


def unprotected_routes(app: FastAPI) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for context in api_route_contexts(app):
        for method in sorted(context.methods or ()):
            key = (method, str(context.path))
            if key not in PUBLIC_ROUTES and not has_auth_dependency(context):
                missing.append(key)
    return missing


def api_route_keys(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, str(context.path))
        for context in api_route_contexts(app)
        for method in context.methods or ()
    }


def test_every_route_is_public_by_design_or_authenticated(app: FastAPI) -> None:
    assert api_route_keys(app), "route enumeration found nothing; the check would be vacuous"
    assert unprotected_routes(app) == []


def test_public_allow_list_has_no_stale_entries(app: FastAPI) -> None:
    assert api_route_keys(app) >= PUBLIC_ROUTES


def test_all_api_routes_are_versioned(app: FastAPI) -> None:
    for _method, path in api_route_keys(app):
        assert path.startswith(API_V1_PREFIX + "/"), path


def test_checker_flags_routes_without_auth() -> None:
    @auth_dependency
    def require_user() -> str:
        return "user"

    def not_auth() -> str:
        return "anything"

    def nested_auth(user: Annotated[str, Depends(require_user)]) -> str:
        return user

    router = APIRouter(prefix="/api/v1/_probe")

    @router.get("/protected")
    async def protected(user: Annotated[str, Depends(require_user)]) -> str:
        return user

    @router.get("/nested")
    async def nested(user: Annotated[str, Depends(nested_auth)]) -> str:
        return user

    @router.get("/open")
    async def open_route(value: Annotated[str, Depends(not_auth)]) -> str:
        return value

    guarded = APIRouter(prefix="/api/v1/_guarded")

    @guarded.get("/by-include")
    async def by_include() -> str:
        return "ok"

    probe = FastAPI()
    probe.include_router(router)
    probe.include_router(guarded, dependencies=[Depends(require_user)])
    assert ("GET", "/api/v1/_guarded/by-include") in api_route_keys(probe)
    assert unprotected_routes(probe) == [("GET", "/api/v1/_probe/open")]


@pytest.mark.parametrize("path", [DOCS_URL, OPENAPI_URL])
def test_docs_are_not_served_in_prod(path: str) -> None:
    prod = Settings.model_validate(
        {
            "env": "prod",
            "db_password": "Zq8vN2kLr5TtY7wPx3Hm",
            "redis_password": "a9F3kQ7mZ2xW8vB4nR6t",
        }
    )
    with TestClient(create_app(prod)) as client:
        assert client.get(path).status_code == 404
