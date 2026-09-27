"""Request correlation id + structured access log (spec §15).

An incoming ``X-Request-ID`` is accepted only if it matches a conservative pattern
(prevents log injection); otherwise a ULID is generated. The id is echoed in the
response header, stored in ``scope["state"]["request_id"]`` (read by the problem+json
handlers), exposed through ``current_request_id()`` and bound to the structlog context.
"""

import re
import secrets
import time
from contextvars import ContextVar
from typing import Final

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ticketward.core.logging import get_logger

REQUEST_ID_HEADER: Final = "X-Request-ID"
_REQUEST_ID_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]{7,127}")
_CROCKFORD32: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_QUIET_ROUTE_PREFIX: Final = "/api/v1/health"
_MAX_LOGGED_PATH: Final = 200

_request_id: ContextVar[str | None] = ContextVar("tw_request_id", default=None)
log = get_logger(__name__)


def new_request_id() -> str:
    """Generate a ULID (26 Crockford base32 chars: 48-bit ms time + 80 random bits).

    Returns:
        A lexicographically time-sortable identifier such as ``01J...``.
    """
    value = (time.time_ns() // 1_000_000) << 80 | secrets.randbits(80)
    return "".join(_CROCKFORD32[(value >> shift) & 0x1F] for shift in range(125, -1, -5))


def is_valid_request_id(value: str) -> bool:
    """Return whether a client-supplied request id is acceptable.

    Args:
        value: Header value.

    Returns:
        ``True`` for 8-128 characters of ``[A-Za-z0-9._:-]`` starting alphanumeric.
    """
    return _REQUEST_ID_RE.fullmatch(value) is not None


def current_request_id() -> str | None:
    """Return the request id of the request being handled, if any."""
    return _request_id.get()


class RequestIdMiddleware:
    """Assign/propagate ``X-Request-ID`` and emit one access-log line per request.

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

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = (
            incoming if incoming is not None and is_valid_request_id(incoming) else new_request_id()
        )
        scope.setdefault("state", {})["request_id"] = request_id
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = _request_id.set(request_id)
        try:
            with structlog.contextvars.bound_contextvars(request_id=request_id):
                try:
                    await self.app(scope, receive, send_wrapper)
                finally:
                    _log_access(scope, status_code, started)
        finally:
            _request_id.reset(token)


def _log_access(scope: Scope, status_code: int, started: float) -> None:
    route = scope.get("route")
    template = getattr(route, "path", None)
    fields: dict[str, object] = {
        "method": scope.get("method"),
        "status": status_code,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if isinstance(template, str):
        fields["route"] = template
    else:
        fields["path"] = str(scope.get("path", ""))[:_MAX_LOGGED_PATH]
    if isinstance(template, str) and template.startswith(_QUIET_ROUTE_PREFIX):
        log.debug("http.request", **fields)
    else:
        log.info("http.request", **fields)
