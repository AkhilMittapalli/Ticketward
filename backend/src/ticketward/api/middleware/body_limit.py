"""Per-route request body limits (spec v1.1 §11 / A-25(g); DoS control, spec §12.2).

Limits are resolved from ``(method, path)`` before routing, from a declarative rule
table built from settings; every route without a rule gets the 64 KB default.

| Route | Default limit |
|---|---|
| ``POST /api/v1/tickets`` | 256 KB (the binding per-ticket byte cap, §6.1) |
| ``POST /api/v1/tickets/batch`` | 2 MB (at most 50 tickets) |
| ``POST /api/v1/kb/documents`` and ``POST /api/v1/kb/documents/{doc_key}/versions`` | 1 MB |
| everything else | 64 KB |

* A declared ``Content-Length`` above the limit is rejected before the app runs.
* Streamed/chunked bodies are counted as they are received; crossing the limit raises
  ``PayloadTooLargeError`` (a 413 ``HTTPException``) inside the app, which the
  problem+json handler renders. If the app does not handle it, this middleware
  answers 413 itself.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPStatus

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ticketward.api import API_V1_PREFIX
from ticketward.api.errors import problem_response
from ticketward.core.config import Settings
from ticketward.schemas.problem import ErrorCode


@dataclass(frozen=True, slots=True)
class BodyLimitRule:
    """A body limit for requests whose method and full path match.

    Attributes:
        name: Short label used in tests and docs.
        method: Upper-case HTTP method.
        path: Pattern that must match the whole request path.
        limit_bytes: Maximum accepted body size.
    """

    name: str
    method: str
    path: re.Pattern[str]
    limit_bytes: int

    def matches(self, method: str, path: str) -> bool:
        """Return whether this rule applies to ``method`` and ``path``."""
        return method == self.method and self.path.fullmatch(path) is not None


def body_limit_rules(settings: Settings) -> tuple[BodyLimitRule, ...]:
    """Build the per-route rule table from settings (spec §11 "Body limits per route").

    Args:
        settings: Application settings.

    Returns:
        Rules for the routes that A-25(g) names; all other routes use the default.
    """
    prefix = re.escape(API_V1_PREFIX)
    return (
        BodyLimitRule(
            "ticket",
            "POST",
            re.compile(prefix + r"/tickets/?"),
            settings.body_limit_ticket_bytes,
        ),
        BodyLimitRule(
            "ticket_batch",
            "POST",
            re.compile(prefix + r"/tickets/batch/?"),
            settings.body_limit_ticket_batch_bytes,
        ),
        BodyLimitRule(
            "kb_document",
            "POST",
            re.compile(prefix + r"/kb/documents/?"),
            settings.body_limit_kb_document_bytes,
        ),
        BodyLimitRule(
            "kb_document_version",
            "POST",
            re.compile(prefix + r"/kb/documents/[^/]+/versions/?"),
            settings.body_limit_kb_document_bytes,
        ),
    )


class PayloadTooLargeError(HTTPException):
    """Raised while receiving a body that exceeds the configured limit.

    Args:
        limit_bytes: The limit that applied, reported to the client.
    """

    def __init__(self, limit_bytes: int) -> None:
        super().__init__(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE.value,
            detail=_detail(limit_bytes),
        )


def _detail(limit_bytes: int) -> str:
    return f"The request body exceeds the {limit_bytes}-byte limit."


class BodyLimitMiddleware:
    """Enforce per-route maximum request body sizes for HTTP requests.

    Args:
        app: Downstream ASGI application.
        default_limit_bytes: Limit for requests that no rule matches.
        rules: Per-route rules; the first match wins.
    """

    def __init__(
        self, app: ASGIApp, default_limit_bytes: int, rules: Sequence[BodyLimitRule] = ()
    ) -> None:
        self.app = app
        self.default_limit_bytes = default_limit_bytes
        self.rules = tuple(rules)

    def limit_for(self, method: str, path: str) -> int:
        """Return the body limit for a request.

        Args:
            method: Request method.
            path: Request path.

        Returns:
            The first matching rule's limit, else the default.
        """
        for rule in self.rules:
            if rule.matches(method, path):
                return rule.limit_bytes
        return self.default_limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.limit_for(str(scope.get("method", "")), str(scope.get("path", "")))
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError:
                declared_size = -1
            if declared_size < 0:
                await problem_response(
                    scope,
                    status_code=HTTPStatus.BAD_REQUEST.value,
                    code=ErrorCode.BAD_REQUEST,
                    detail="The Content-Length header is invalid.",
                )(scope, receive, send)
                return
            if declared_size > limit:
                await _reject(limit, scope, receive, send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise PayloadTooLargeError(limit)
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except PayloadTooLargeError:
            if response_started:
                raise
            await _reject(limit, scope, receive, send)


async def _reject(limit: int, scope: Scope, receive: Receive, send: Send) -> None:
    response = problem_response(
        scope,
        status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE.value,
        code=ErrorCode.PAYLOAD_TOO_LARGE,
        detail=_detail(limit),
        headers={"Connection": "close"},
    )
    await response(scope, receive, send)
