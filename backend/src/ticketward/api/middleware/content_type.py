"""JSON-only request bodies (spec v1.1 §11, A-25(g)).

An unsafe request (POST, PUT, PATCH, DELETE) that carries a body in any media type other
than ``application/json`` gets ``415 UNSUPPORTED_MEDIA_TYPE``. This also defeats form
and ``text/plain`` CSRF (spec §12.7, CSRF step 3). Media-type parameters such as
``charset`` are allowed; bodiless unsafe requests and safe methods are not checked.
"""

from http import HTTPStatus
from typing import Final

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from ticketward.api.errors import problem_response
from ticketward.schemas.problem import ErrorCode

JSON_MEDIA_TYPE: Final = "application/json"
UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_json_media_type(content_type: str | None) -> bool:
    """Return whether a ``Content-Type`` value is ``application/json``.

    Args:
        content_type: Raw header value, or ``None`` when absent.

    Returns:
        ``True`` for ``application/json`` with or without parameters (case-insensitive).
    """
    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() == JSON_MEDIA_TYPE


def _declares_body(headers: Headers) -> bool:
    content_length = headers.get("content-length")
    if content_length is not None:
        try:
            return int(content_length) > 0
        except ValueError:
            return True  # malformed lengths are answered with 400 by the body limiter
    return "transfer-encoding" in headers


class JsonBodyMiddleware:
    """Reject non-JSON bodies on unsafe methods with a 415 problem response.

    Args:
        app: Downstream ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection."""
        if scope["type"] != "http" or scope.get("method") not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if _declares_body(headers) and not is_json_media_type(headers.get("content-type")):
            await problem_response(
                scope,
                status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE.value,
                code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)
