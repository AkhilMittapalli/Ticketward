"""Integration tests against real Postgres (pgvector image) and Redis.

Skipped unless both variables are set, e.g. with ``make up`` running::

    TW_TEST_DATABASE_URL=postgresql+asyncpg://ticketward:<pw>@127.0.0.1:5432/ticketward
    TW_TEST_REDIS_URL=redis://127.0.0.1:6379/0      # + TW_TEST_REDIS_PASSWORD if required

CI provides both via service containers (``.github/workflows/ci.yml``). P4 moves these
to testcontainers (spec §14.3).
"""

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text

from ticketward.core.config import Environment, Settings
from ticketward.core.redis import create_redis_client
from ticketward.db.session import create_db_engine
from ticketward.services.health import DatabaseHealthCheck, RedisHealthCheck, run_checks

DATABASE_URL = os.environ.get("TW_TEST_DATABASE_URL")
REDIS_URL = os.environ.get("TW_TEST_REDIS_URL")
REDIS_PASSWORD = os.environ.get("TW_TEST_REDIS_PASSWORD")
REQUIRED_EXTENSIONS = {"pgcrypto", "vector", "citext", "pg_trgm"}

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and REDIS_URL),
    reason="set TW_TEST_DATABASE_URL and TW_TEST_REDIS_URL to run integration tests",
)


def _settings() -> Settings:
    assert DATABASE_URL is not None
    assert REDIS_URL is not None
    return Settings.model_validate(
        {
            "env": Environment.test,
            "database_url": SecretStr(DATABASE_URL),
            "redis_url": REDIS_URL,
            "redis_password": SecretStr(REDIS_PASSWORD) if REDIS_PASSWORD else None,
        }
    )


async def test_readiness_checks_pass_against_real_services() -> None:
    settings = _settings()
    engine = create_db_engine(settings)
    redis = create_redis_client(settings)
    try:
        outcomes = await run_checks(
            [DatabaseHealthCheck(engine), RedisHealthCheck(redis)], timeout_s=5.0
        )
    finally:
        await redis.aclose()
        await engine.dispose()
    assert all(outcome.ok for outcome in outcomes)


async def _installed_extensions(settings: Settings) -> set[str]:
    engine = create_db_engine(settings)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT extname FROM pg_extension"))
            return {row[0] for row in rows}
    finally:
        await engine.dispose()


def test_migrations_upgrade_downgrade_upgrade(
    backend_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert DATABASE_URL is not None
    monkeypatch.setenv("TW_ENV", "test")
    monkeypatch.setenv("TW_DATABASE_URL", DATABASE_URL)
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))

    command.upgrade(config, "head")
    assert asyncio.run(_installed_extensions(_settings())) >= REQUIRED_EXTENSIONS
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert asyncio.run(_installed_extensions(_settings())) >= REQUIRED_EXTENSIONS
