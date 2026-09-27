"""Application factory (spec §14.1 ``main.py``).

Run with the factory flag so nothing is constructed at import time::

    uvicorn --factory ticketward.main:create_app
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from ticketward import __version__
from ticketward.api.errors import UnhandledErrorMiddleware, register_exception_handlers
from ticketward.api.middleware.body_limit import BodyLimitMiddleware, body_limit_rules
from ticketward.api.middleware.content_type import JsonBodyMiddleware
from ticketward.api.middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from ticketward.api.middleware.security_headers import SecurityHeadersMiddleware
from ticketward.api.routers import ROUTERS
from ticketward.core.config import Settings, get_settings
from ticketward.core.logging import configure_logging, get_logger
from ticketward.core.redis import create_redis_client
from ticketward.db.session import create_db_engine, create_session_factory
from ticketward.schemas.problem import PROBLEM_MEDIA_TYPE, ProblemDetail
from ticketward.services.health import DatabaseHealthCheck, RedisHealthCheck

API_TITLE: Final = "Ticketward API"
OPENAPI_URL: Final = "/api/openapi.json"
DOCS_URL: Final = "/api/docs"

DEFAULT_ERROR_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    "4XX": {"model": ProblemDetail, "description": "Client error (RFC 9457 problem details)."},
    "5XX": {"model": ProblemDetail, "description": "Server error (RFC 9457 problem details)."},
}

log = get_logger(__name__)


class TicketwardAPI(FastAPI):
    """FastAPI subclass whose OpenAPI documents errors as ``application/problem+json``."""

    def openapi(self) -> dict[str, Any]:
        """Generate (once) and return the OpenAPI document.

        Returns:
            The OpenAPI 3.1 schema with problem responses under the problem media type.
        """
        already_built = self.openapi_schema is not None
        schema = super().openapi()
        if not already_built:
            _use_problem_media_type(schema)
        return schema


def _use_problem_media_type(schema: dict[str, Any]) -> None:
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            for status, response in operation.get("responses", {}).items():
                if not (status.startswith(("4", "5")) or status == "default"):
                    continue
                content = response.get("content", {})
                json_content = content.get("application/json")
                ref = (json_content or {}).get("schema", {}).get("$ref", "")
                if ref.endswith("/ProblemDetail"):
                    content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")


def _operation_id(route: APIRoute) -> str:
    """Stable, readable operation ids for OpenAPI clients (``health_live``)."""
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create backing-service clients on startup and release them on shutdown.

    Startup never fails because a dependency is down: liveness stays green and the
    readiness probe reports the outage instead.

    Args:
        app: The application being served.

    Yields:
        Control while the application serves requests.
    """
    settings: Settings = app.state.settings
    engine = create_db_engine(settings)
    redis = create_redis_client(settings)
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = redis
    app.state.readiness_checks = (DatabaseHealthCheck(engine), RedisHealthCheck(redis))
    log.info("app.startup", env=settings.env.value, version=__version__)
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()
        log.info("app.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    Args:
        settings: Explicit settings (tests); loaded from the environment when omitted.

    Returns:
        The configured FastAPI application.
    """
    settings = settings if settings is not None else get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    docs_enabled = settings.openapi_enabled
    app = TicketwardAPI(
        title=API_TITLE,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        openapi_url=OPENAPI_URL if docs_enabled else None,
        docs_url=DOCS_URL if docs_enabled else None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        generate_unique_id_function=_operation_id,
        responses=DEFAULT_ERROR_RESPONSES,
    )
    app.state.settings = settings
    register_exception_handlers(app)

    # add_middleware prepends: the last one added is the outermost.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(JsonBodyMiddleware)
    app.add_middleware(
        BodyLimitMiddleware,
        default_limit_bytes=settings.body_limit_default_bytes,
        rules=body_limit_rules(settings),
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "Idempotency-Key", "X-CSRF-Token", REQUEST_ID_HEADER],
            expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
            max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware, docs_paths=(DOCS_URL,) if docs_enabled else ())
    app.add_middleware(RequestIdMiddleware)

    for router in ROUTERS:
        app.include_router(router)
    return app
