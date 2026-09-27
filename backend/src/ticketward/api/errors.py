"""RFC 9457 ``application/problem+json`` error handling (spec §11, ADR-0025).

Rules:

* Every error response is a ``ProblemDetail`` with a stable ``code`` and the
  ``request_id`` that correlates with server logs.
* Client-facing ``detail`` text is always chosen by our code. Exception messages,
  stack traces and submitted input values are never echoed (no ``detail=str(e)``).
* Unexpected exceptions are logged server-side (redacted) and answered with a generic
  ``INTERNAL`` problem by ``UnhandledErrorMiddleware``. That middleware sits inside the
  request-id and security-header middleware, so 500 responses carry both.
"""

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ticketward.core.logging import get_logger
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
from ticketward.schemas.problem import (
    PROBLEM_MEDIA_TYPE,
    ErrorCode,
    FieldError,
    ProblemDetail,
    problem_type_uri,
)

log = get_logger(__name__)

MAX_FIELD_ERRORS: Final = 50

TITLES: Final[Mapping[ErrorCode, str]] = {
    ErrorCode.BAD_REQUEST: "Bad request",
    ErrorCode.VALIDATION_ERROR: "Request validation failed",
    ErrorCode.UNAUTHENTICATED: "Authentication required",
    ErrorCode.FORBIDDEN: "Forbidden",
    ErrorCode.CSRF_FAILED: "CSRF validation failed",
    ErrorCode.DEMO_LOCKED: "Disabled in the demo",
    ErrorCode.NOT_FOUND: "Resource not found",
    ErrorCode.METHOD_NOT_ALLOWED: "Method not allowed",
    ErrorCode.CONFLICT: "Conflict",
    ErrorCode.REFRESH_SUPERSEDED: "Refresh superseded",
    ErrorCode.IDEMPOTENCY_MISMATCH: "Idempotency key mismatch",
    ErrorCode.PAYLOAD_TOO_LARGE: "Payload too large",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "Unsupported media type",
    ErrorCode.RATE_LIMITED: "Too many requests",
    ErrorCode.UPSTREAM_UNAVAILABLE: "Service unavailable",
    ErrorCode.MAINTENANCE: "Maintenance in progress",
    ErrorCode.INTERNAL: "Internal server error",
}

DEFAULT_DETAILS: Final[Mapping[ErrorCode, str]] = {
    ErrorCode.BAD_REQUEST: "The request could not be processed.",
    ErrorCode.VALIDATION_ERROR: "One or more fields are invalid.",
    ErrorCode.UNAUTHENTICATED: "Authentication is required to access this resource.",
    ErrorCode.FORBIDDEN: "You do not have permission to perform this action.",
    ErrorCode.CSRF_FAILED: "The CSRF token is missing or invalid.",
    ErrorCode.DEMO_LOCKED: "This action is disabled in the public demo.",
    ErrorCode.NOT_FOUND: "The requested resource was not found.",
    ErrorCode.METHOD_NOT_ALLOWED: "The HTTP method is not allowed for this resource.",
    ErrorCode.CONFLICT: "The request conflicts with the current state of the resource.",
    ErrorCode.REFRESH_SUPERSEDED: "The session was refreshed by a concurrent request. Retry once.",
    ErrorCode.IDEMPOTENCY_MISMATCH: (
        "The Idempotency-Key was already used with a different request."
    ),
    ErrorCode.PAYLOAD_TOO_LARGE: "The request body is too large.",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "Request bodies must be sent as application/json.",
    ErrorCode.RATE_LIMITED: "Too many requests. Retry later.",
    ErrorCode.UPSTREAM_UNAVAILABLE: "A required upstream service is temporarily unavailable.",
    ErrorCode.MAINTENANCE: "The service is in a scheduled maintenance window. Retry later.",
    ErrorCode.INTERNAL: (
        "An unexpected error occurred. Quote the request_id when contacting support."
    ),
}

_STATUS_TO_CODE: Final[Mapping[int, ErrorCode]] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    502: ErrorCode.UPSTREAM_UNAVAILABLE,
    503: ErrorCode.UPSTREAM_UNAVAILABLE,
    504: ErrorCode.UPSTREAM_UNAVAILABLE,
}
"""Status-only fallback. Codes that share a status (DEMO_LOCKED, REFRESH_SUPERSEDED,
MAINTENANCE) are only produced by their dedicated domain errors."""

_DOMAIN_ERRORS: Final[Mapping[type[DomainError], tuple[int, ErrorCode]]] = {
    NotFoundError: (404, ErrorCode.NOT_FOUND),
    RefreshSupersededError: (409, ErrorCode.REFRESH_SUPERSEDED),
    ConflictError: (409, ErrorCode.CONFLICT),
    IdempotencyMismatchError: (422, ErrorCode.IDEMPOTENCY_MISMATCH),
    DemoLockedError: (403, ErrorCode.DEMO_LOCKED),
    PermissionDeniedError: (403, ErrorCode.FORBIDDEN),
    RateLimitedError: (429, ErrorCode.RATE_LIMITED),
    MaintenanceError: (503, ErrorCode.MAINTENANCE),
    UpstreamUnavailableError: (503, ErrorCode.UPSTREAM_UNAVAILABLE),
    DomainError: (400, ErrorCode.BAD_REQUEST),
}


def code_for_status(status_code: int) -> ErrorCode:
    """Map an HTTP status to the closest ``ErrorCode``.

    Args:
        status_code: HTTP status.

    Returns:
        The mapped code; unmapped 4xx map to ``BAD_REQUEST`` and 5xx to ``INTERNAL``.
    """
    if status_code in _STATUS_TO_CODE:
        return _STATUS_TO_CODE[status_code]
    return ErrorCode.INTERNAL if status_code >= 500 else ErrorCode.BAD_REQUEST  # noqa: PLR2004


def request_id_from_scope(scope: Scope) -> str | None:
    """Return the request id stored by ``RequestIdMiddleware``, if any.

    Args:
        scope: ASGI connection scope.

    Returns:
        The request id or ``None``.
    """
    state = scope.get("state")
    if isinstance(state, Mapping):
        value = state.get("request_id")
        if isinstance(value, str):
            return value
    return None


def problem_response(
    scope: Scope,
    *,
    status_code: int,
    code: ErrorCode,
    detail: str | None = None,
    errors: Sequence[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build an ``application/problem+json`` response.

    Args:
        scope: ASGI scope of the failing request (for ``instance`` and ``request_id``).
        status_code: HTTP status.
        code: Stable error code.
        detail: Client-safe detail; defaults to the code's generic text.
        errors: Field errors for validation failures.
        headers: Extra response headers (e.g. ``Retry-After``, ``Allow``).

    Returns:
        The problem response.
    """
    path = scope.get("path")
    problem = ProblemDetail(
        type=problem_type_uri(code),
        title=TITLES[code],
        status=status_code,
        detail=detail or DEFAULT_DETAILS[code],
        instance=path if isinstance(path, str) else None,
        code=code,
        request_id=request_id_from_scope(scope),
        errors=list(errors) if errors is not None else None,
    )
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=status_code,
        headers=dict(headers) if headers else None,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _field_errors(raw_errors: Sequence[Any]) -> list[FieldError]:
    field_errors: list[FieldError] = []
    for raw in raw_errors[:MAX_FIELD_ERRORS]:
        if not isinstance(raw, Mapping):
            continue
        loc = raw.get("loc", ())
        loc_items = loc if isinstance(loc, list | tuple) else (loc,)
        field_errors.append(
            FieldError(
                loc=[part if isinstance(part, str | int) else str(part) for part in loc_items],
                msg=str(raw.get("msg", "Invalid value."))[:256],
                type=str(raw.get("type", "value_error"))[:64],
            )
        )
    return field_errors


def _safe_http_detail(exc: StarletteHTTPException) -> str | None:
    """Return the exception detail if it is safe and more useful than our default."""
    if exc.status_code >= 500 or not isinstance(exc.detail, str):  # noqa: PLR2004
        return None  # 5xx detail is never passed through
    try:
        reason_phrase = HTTPStatus(exc.status_code).phrase
    except ValueError:
        reason_phrase = ""
    return None if exc.detail in {"", reason_phrase} else exc.detail


def _domain_mapping(exc: DomainError) -> tuple[int, ErrorCode]:
    for cls in type(exc).__mro__:
        if cls in _DOMAIN_ERRORS:
            return _DOMAIN_ERRORS[cls]
    return _DOMAIN_ERRORS[DomainError]  # pragma: no cover - DomainError is always in the MRO


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    raw_errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    return problem_response(
        request.scope,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY.value,
        code=ErrorCode.VALIDATION_ERROR,
        errors=_field_errors(raw_errors),
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        return await _unexpected_error_handler(request, exc)
    return problem_response(
        request.scope,
        status_code=exc.status_code,
        code=code_for_status(exc.status_code),
        detail=_safe_http_detail(exc),
        headers=exc.headers,
    )


async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        return await _unexpected_error_handler(request, exc)
    status_code, code = _domain_mapping(exc)
    retry_after = (
        exc.retry_after_s if isinstance(exc, RateLimitedError | MaintenanceError) else None
    )
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    if status_code >= 500:  # noqa: PLR2004
        log.warning("http.upstream_unavailable", error_type=type(exc).__name__)
    return problem_response(
        request.scope,
        status_code=status_code,
        code=code,
        detail=exc.public_message,
        headers=headers,
    )


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler used by Starlette's ``ServerErrorMiddleware``.

    Only reached when an exception escapes our own middleware stack, so it adds the
    minimal hardening headers itself.
    """
    log.error("http.unhandled_exception", error_type=type(exc).__name__, exc_info=exc)
    request_id = request_id_from_scope(request.scope)
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    }
    if request_id:
        headers["X-Request-ID"] = request_id
    return problem_response(
        request.scope,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
        code=ErrorCode.INTERNAL,
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install the problem+json handlers on ``app``.

    Args:
        app: Application to configure.
    """
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)


class UnhandledErrorMiddleware:
    """Convert unexpected exceptions into a generic ``INTERNAL`` problem response.

    Placed innermost among the user middlewares so the response still passes through
    the request-id and security-header middlewares. The exception is logged with
    its traceback (redacted) and is not re-raised once a response has been sent.

    Args:
        app: Downstream ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            log.error(
                "http.unhandled_exception",
                method=scope.get("method"),
                error_type=type(exc).__name__,
                exc_info=exc,
            )
            if response_started:
                raise
            response = problem_response(
                scope, status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value, code=ErrorCode.INTERNAL
            )
            await response(scope, receive, send)
