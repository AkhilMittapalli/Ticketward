"""Security response headers (spec §12.7).

The API only serves JSON, so it uses a stricter CSP than the web UI
(``default-src 'none'``). Swagger UI (non-prod only) gets a relaxed, docs-scoped CSP
because it loads its assets from jsDelivr and bootstraps with an inline script.
The web UI's nonce-based CSP is set by the Next.js app / reverse proxy (P8/P9).

Headers are only added when absent, so a route can deliberately override one.
"""

from collections.abc import Iterable
from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP: Final = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CSP: Final = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

BASE_SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("Strict-Transport-Security", "max-age=63072000; includeSubDomains"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    (
        "Permissions-Policy",
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=()",
    ),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("X-Frame-Options", "DENY"),
)

_API_PREFIX: Final = "/api"


class SecurityHeadersMiddleware:
    """Add hardening headers to every HTTP response.

    Args:
        app: Downstream ASGI application.
        docs_paths: Exact paths that serve Swagger UI and receive ``DOCS_CSP``.
    """

    def __init__(self, app: ASGIApp, docs_paths: Iterable[str] = ()) -> None:
        self.app = app
        self.docs_paths = frozenset(docs_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        csp = DOCS_CSP if path in self.docs_paths else API_CSP
        no_store = path == _API_PREFIX or path.startswith(_API_PREFIX + "/")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in BASE_SECURITY_HEADERS:
                    headers.setdefault(name, value)
                headers.setdefault("Content-Security-Policy", csp)
                if no_store:
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_wrapper)
