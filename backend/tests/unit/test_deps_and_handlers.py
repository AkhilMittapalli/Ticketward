"""Defensive branches: misconfigured apps and handlers invoked with unexpected types."""

from collections.abc import Awaitable, Callable

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ticketward.api.deps import auth_dependency, get_app_settings, get_readiness_checks
from ticketward.api.errors import (
    _domain_error_handler,
    _field_errors,
    _http_exception_handler,
    _validation_error_handler,
)
from ticketward.domain.errors import UpstreamUnavailableError


def _request(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app, "path": "/api/v1/x", "headers": []})


def test_settings_dependency_requires_create_app() -> None:
    with pytest.raises(RuntimeError, match="create_app"):
        get_app_settings(_request(FastAPI()))


def test_readiness_dependency_fails_closed() -> None:
    app = FastAPI()
    app.state.readiness_checks = ()
    with pytest.raises(UpstreamUnavailableError):
        get_readiness_checks(_request(app))


def test_auth_dependency_marks_callables() -> None:
    def require_admin() -> None:
        return None

    marked = auth_dependency(require_admin)
    assert marked is require_admin
    assert getattr(require_admin, "__rf_auth_dependency__", False) is True


def test_field_errors_tolerate_unusual_error_shapes() -> None:
    errors = _field_errors(["not-a-mapping", {"loc": "body", "msg": "x" * 400}, {}])
    assert [error.loc for error in errors] == [["body"], []]
    assert len(errors[0].msg) == 256
    assert errors[0].type == "value_error"
    assert errors[1].msg == "Invalid value."


@pytest.mark.parametrize(
    "handler", [_http_exception_handler, _domain_error_handler, _validation_error_handler]
)
async def test_handlers_given_the_wrong_exception_type_fail_safe(
    handler: Callable[[Request, Exception], Awaitable[JSONResponse]],
) -> None:
    response = await handler(_request(FastAPI()), ValueError("secret detail"))
    assert response.status_code in {422, 500}
    assert b"secret detail" not in response.body
