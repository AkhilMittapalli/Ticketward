"""Readiness checks for backing services (spec §15 "Health").

Each check raises on failure. ``run_checks`` runs them concurrently, bounds each with a
timeout, and reports only ``ok``/not-ok per component; failure details are logged
server-side by exception type only (exception messages can contain hosts or DSNs).
"""

import asyncio
import inspect
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ticketward.core.logging import get_logger

log = get_logger(__name__)


class HealthCheck(Protocol):
    """A dependency probe used by ``GET /api/v1/health/ready``."""

    @property
    def name(self) -> str:
        """Stable component name reported to clients (e.g. ``db``)."""
        ...

    async def check(self) -> None:
        """Return normally when healthy; raise any exception when not."""
        ...


class SupportsPing(Protocol):
    """Minimal Redis client surface used by ``RedisHealthCheck``."""

    def ping(self) -> Awaitable[bool] | bool:
        """Send ``PING``."""
        ...


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """Result of one readiness check.

    Attributes:
        name: Component name.
        ok: Whether the check passed within its timeout.
    """

    name: str
    ok: bool


class DatabaseHealthCheck:
    """Checks that Postgres accepts connections and answers ``SELECT 1``.

    Args:
        engine: Application async engine.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @property
    def name(self) -> str:
        """Component name."""
        return "db"

    async def check(self) -> None:
        """Run ``SELECT 1`` on a pooled connection."""
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))


class RedisHealthCheck:
    """Checks that Redis answers ``PING``.

    Args:
        client: Redis client (``redis.asyncio.Redis``).
    """

    def __init__(self, client: SupportsPing) -> None:
        self._client = client

    @property
    def name(self) -> str:
        """Component name."""
        return "redis"

    async def check(self) -> None:
        """Send ``PING`` and require a truthy reply.

        Raises:
            ConnectionError: If Redis replies with a falsy value.
        """
        reply = self._client.ping()
        ok = await reply if inspect.isawaitable(reply) else reply
        if not ok:
            msg = "redis PING returned a falsy reply"
            raise ConnectionError(msg)


async def _run_one(check: HealthCheck, timeout_s: float) -> CheckOutcome:
    try:
        async with asyncio.timeout(timeout_s):
            await check.check()
    except Exception as exc:  # any failure means "not ready"; never propagate
        log.warning("health.check_failed", component=check.name, error_type=type(exc).__name__)
        return CheckOutcome(name=check.name, ok=False)
    return CheckOutcome(name=check.name, ok=True)


async def run_checks(checks: Sequence[HealthCheck], timeout_s: float) -> list[CheckOutcome]:
    """Run readiness checks concurrently.

    Args:
        checks: Checks to run.
        timeout_s: Per-check timeout in seconds.

    Returns:
        One outcome per check, in input order.
    """
    return list(await asyncio.gather(*(_run_one(check, timeout_s) for check in checks)))
