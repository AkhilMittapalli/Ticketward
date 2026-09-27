"""Application settings (spec §12.6, §14.2; 12-factor).

Values come from ``TW_*`` environment variables and from secret files in the secrets
directory (Docker secrets mounted at ``/run/secrets``; override with ``TW_SECRETS_DIR``).
A secret file is named after the variable in lower case, e.g. ``tw_db_password``.

In ``prod`` the service refuses to boot (``ValidationError``) when debug or API docs are
on, CORS is opened, logs are not JSON, or any secret is missing, short, or a
placeholder. The error lists the offending settings by name and never echoes values.
"""

import json
import os
from decimal import Decimal
from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Final, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_SECRETS_DIR: Final = "/run/secrets"
SECRETS_DIR_ENV: Final = "TW_SECRETS_DIR"
MIN_PROD_SECRET_LENGTH: Final = 16
MAX_BODY_LIMIT_BYTES: Final = 3_000_000
"""Upper bound for any per-route body limit: the edge cap (Caddy ``3MB``, spec §24.2)
sits just above the largest route limit, so the API's limits always decide."""
_PLACEHOLDER_MARKERS: Final = (
    "change",
    "placeholder",
    "example",
    "replace",
    "dummy",
    "todo",
    "xxxx",
    "default",
    "secret",
    "password",
)

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@unique
class Environment(StrEnum):
    """Deployment environment."""

    dev = "dev"
    test = "test"
    prod = "prod"


def secret_problem(value: str | None) -> str | None:
    """Explain why a secret value is unacceptable in production.

    Args:
        value: Plain secret value, or ``None`` when unset.

    Returns:
        A short reason (never containing the value), or ``None`` if acceptable.
    """
    if value is None or not value.strip():
        return "is not set"
    if len(value) < MIN_PROD_SECRET_LENGTH:
        return f"is shorter than {MIN_PROD_SECRET_LENGTH} characters"
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return "looks like a placeholder or default value"
    return None


def _validate_origin(origin: str) -> str:
    parts = urlsplit(origin)
    if origin == "*" or "*" in origin:
        msg = "wildcard CORS origins are not allowed"
        raise ValueError(msg)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        msg = "CORS origins must be absolute http(s) origins"
        raise ValueError(msg)
    if parts.path not in {"", "/"} or parts.query or parts.fragment or parts.username:
        msg = "CORS origins must not contain a path, query, fragment or credentials"
        raise ValueError(msg)
    return f"{parts.scheme}://{parts.netloc}"


class Settings(BaseSettings):
    """Runtime configuration for the API, worker and migrations.

    Attributes:
        env: Deployment environment. Defaults to ``prod`` so an unconfigured
            deployment fails closed.
        service_name: Logical service name used in logs and ``application_name``.
        debug: Framework debug mode (tracebacks in HTML error pages). Dev only.
        docs_enabled: Serve OpenAPI + Swagger UI. ``None`` means "on unless prod".
        log_level: Root log level.
        log_json: Emit JSON logs (required in prod); console rendering otherwise.
        database_url: Full ``postgresql+asyncpg://`` DSN. Overrides the ``db_*`` parts.
        db_host: Postgres host.
        db_port: Postgres port.
        db_name: Postgres database.
        db_user: Postgres role.
        db_password: Postgres password (secret file ``tw_db_password`` in Compose).
        db_pool_size: SQLAlchemy pool size per process.
        db_max_overflow: Extra connections above ``db_pool_size``.
        db_pool_timeout_s: Seconds to wait for a pooled connection.
        db_connect_timeout_s: Seconds to wait for a new connection.
        db_command_timeout_s: Per-statement timeout enforced by asyncpg.
        redis_url: Redis URL without credentials (``redis://`` or ``rediss://``).
        redis_password: Redis ``requirepass`` (secret file ``tw_redis_password``).
        redis_socket_timeout_s: Redis connect/read timeout.
        cors_origins: Browser origins allowed with credentials (dev only; must be
            empty in prod where the UI and API are same-origin, spec §12.7).
        body_limit_default_bytes: Body cap for every route without its own limit
            (spec §11 / A-25(g): 64 KB).
        body_limit_ticket_bytes: Body cap for ``POST /tickets`` (256 KB, the binding
            per-ticket byte cap, spec §6.1).
        body_limit_ticket_batch_bytes: Body cap for ``POST /tickets/batch`` (2 MB).
        body_limit_kb_document_bytes: Body cap for KB document bodies,
            ``POST /kb/documents`` and ``POST /kb/documents/{doc_key}/versions`` (1 MB).
        ready_check_timeout_s: Timeout for each readiness dependency check.
        frontier_enabled: Global kill switch for frontier routing (P7). Off by default.
        frontier_daily_budget_usd: Daily frontier spend cap (spec §7.5).
    """

    model_config = SettingsConfigDict(
        env_prefix="TW_",
        case_sensitive=False,
        env_ignore_empty=True,  # `TW_X=` behaves like "unset" (Compose/.env friendly)
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        validate_default=True,
    )

    env: Environment = Environment.prod
    service_name: str = Field(default="ticketward-api", pattern=r"^[a-z][a-z0-9-]{2,63}$")
    debug: bool = False
    docs_enabled: bool | None = None
    log_level: LogLevel = "INFO"
    log_json: bool = True

    database_url: SecretStr | None = None
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "ticketward"
    db_user: str = "ticketward"
    db_password: SecretStr | None = None
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=5, ge=0, le=100)
    db_pool_timeout_s: float = Field(default=10.0, gt=0, le=120)
    db_connect_timeout_s: float = Field(default=5.0, gt=0, le=60)
    db_command_timeout_s: float = Field(default=30.0, gt=0, le=600)

    redis_url: str = "redis://localhost:6379/0"
    redis_password: SecretStr | None = None
    redis_socket_timeout_s: float = Field(default=2.0, gt=0, le=60)

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    body_limit_default_bytes: int = Field(default=65_536, ge=1024, le=MAX_BODY_LIMIT_BYTES)
    body_limit_ticket_bytes: int = Field(default=262_144, ge=1024, le=MAX_BODY_LIMIT_BYTES)
    body_limit_ticket_batch_bytes: int = Field(default=2_097_152, ge=1024, le=MAX_BODY_LIMIT_BYTES)
    body_limit_kb_document_bytes: int = Field(default=1_048_576, ge=1024, le=MAX_BODY_LIMIT_BYTES)
    ready_check_timeout_s: float = Field(default=2.0, gt=0, le=30)

    frontier_enabled: bool = False
    frontier_daily_budget_usd: Decimal = Field(default=Decimal("2.00"), ge=0, le=1000)

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and urlsplit(value.get_secret_value()).scheme != "postgresql+asyncpg":
            msg = "database_url must use the postgresql+asyncpg:// scheme"
            raise ValueError(msg)
        return value

    @field_validator("redis_url")
    @classmethod
    def _check_redis_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"redis", "rediss"} or not parts.hostname:
            msg = "redis_url must be a redis:// or rediss:// URL with a host"
            raise ValueError(msg)
        if parts.password is not None or parts.username is not None:
            msg = "redis_url must not embed credentials; use TW_REDIS_PASSWORD or its secret file"
            raise ValueError(msg)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _check_cors_origins(cls, value: list[str]) -> list[str]:
        return [_validate_origin(origin) for origin in value]

    @model_validator(mode="after")
    def _enforce_production_rules(self) -> Self:
        if self.env is not Environment.prod:
            return self
        problems: list[str] = []
        if self.debug:
            problems.append("TW_DEBUG must be false")
        if self.docs_enabled:
            problems.append("TW_DOCS_ENABLED must be false")
        if not self.log_json:
            problems.append("TW_LOG_JSON must be true")
        if self.cors_origins:
            problems.append("TW_CORS_ORIGINS must be empty (same-origin via reverse proxy)")
        db_reason = secret_problem(self._effective_db_password())
        if db_reason:
            problems.append(f"the database password {db_reason}")
        redis_reason = secret_problem(
            self.redis_password.get_secret_value() if self.redis_password else None
        )
        if redis_reason:
            problems.append(f"TW_REDIS_PASSWORD {redis_reason}")
        if problems:
            msg = "refusing to start in prod: " + "; ".join(problems)
            raise ValueError(msg)
        return self

    def _effective_db_password(self) -> str | None:
        if self.database_url is not None:
            return urlsplit(self.database_url.get_secret_value()).password
        return self.db_password.get_secret_value() if self.db_password else None

    @property
    def openapi_enabled(self) -> bool:
        """Whether OpenAPI and Swagger UI are served (never in prod)."""
        if self.docs_enabled is not None:
            return self.docs_enabled
        return self.env is not Environment.prod


def resolve_secrets_dir() -> Path | None:
    """Return the secrets directory if it exists.

    Returns:
        ``TW_SECRETS_DIR`` (default ``/run/secrets``) when it is a directory, else ``None``.
    """
    candidate = Path(os.environ.get(SECRETS_DIR_ENV, DEFAULT_SECRETS_DIR))
    return candidate if candidate.is_dir() else None


def get_settings() -> Settings:
    """Load settings from the environment and the secrets directory.

    Returns:
        Validated, immutable settings.

    Raises:
        pydantic.ValidationError: If a value is invalid or a prod rule is violated.
    """
    return Settings(_secrets_dir=resolve_secrets_dir())
