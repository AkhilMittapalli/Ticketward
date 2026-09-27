"""Shared fixtures.

Unit tests never touch real Postgres/Redis: the lifespan creates lazy clients only,
and readiness is exercised through fake checks. Integration tests (tests/integration)
run only when ``TW_TEST_DATABASE_URL``/``TW_TEST_REDIS_URL`` point at real services.

Helpers are exposed as fixtures because ``--import-mode=importlib`` keeps test modules
from importing each other.
"""

import asyncio
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ticketward.api.deps import get_readiness_checks
from ticketward.core.config import Environment, Settings
from ticketward.core.logging import configure_logging
from ticketward.main import create_app
from ticketward.services.health import HealthCheck

TESTS_DIR = Path(__file__).resolve().parent

_DIR_MARKERS = {
    "unit": pytest.mark.unit,
    "integration": pytest.mark.integration,
    "security": pytest.mark.security,
    "property": pytest.mark.property,
    "contract": pytest.mark.contract,
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply the marker named after each test's top-level directory."""
    for item in items:
        relative = item.path.resolve().relative_to(TESTS_DIR)
        marker = _DIR_MARKERS.get(relative.parts[0]) if len(relative.parts) > 1 else None
        if marker is not None:
            item.add_marker(marker)


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip developer TW_* variables (except TW_TEST_*) so tests are reproducible."""
    for key in list(os.environ):
        upper = key.upper()
        if upper.startswith("TW_") and not upper.startswith("TW_TEST_"):
            monkeypatch.delenv(key)


@pytest.fixture(autouse=True)
def _rebind_logging() -> Iterator[None]:
    """Re-bind the log handler after each test (``capsys`` swaps ``sys.stdout``)."""
    yield
    configure_logging(level="DEBUG", json_logs=True)


@dataclass
class FakeCheck:
    """Readiness check double whose outcome and latency are controlled by the test."""

    name: str
    ok: bool = True
    delay_s: float = 0.0
    calls: int = 0

    async def check(self) -> None:
        self.calls += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if not self.ok:
            # Deliberately sensitive-looking text: it must never reach clients.
            msg = "connection refused by 10.0.0.5:5432 for user rf password=hunter2"
            raise ConnectionRefusedError(msg)


type CheckFactory = Callable[..., FakeCheck]
type SettingsFactory = Callable[..., Settings]
type ChecksOverride = Callable[[FastAPI, list[HealthCheck]], None]


@pytest.fixture
def repo_root() -> Path:
    return TESTS_DIR.parent.parent


@pytest.fixture
def backend_dir() -> Path:
    return TESTS_DIR.parent


@pytest.fixture
def check_factory() -> CheckFactory:
    """Build ``FakeCheck`` instances: ``check_factory("db", ok=False)``."""

    def make(name: str, *, ok: bool = True, delay_s: float = 0.0) -> FakeCheck:
        return FakeCheck(name=name, ok=ok, delay_s=delay_s)

    return make


@pytest.fixture
def settings_factory() -> SettingsFactory:
    """Build test-environment settings with explicit overrides."""

    def make(**overrides: object) -> Settings:
        values: dict[str, object] = {"env": Environment.test, "log_level": "DEBUG"}
        values.update(overrides)
        return Settings.model_validate(values)

    return make


@pytest.fixture
def settings(settings_factory: SettingsFactory) -> Settings:
    return settings_factory()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def override_checks() -> ChecksOverride:
    """Replace the readiness checks registered by the lifespan."""

    def install(app: FastAPI, checks: list[HealthCheck]) -> None:
        app.dependency_overrides[get_readiness_checks] = lambda: checks

    return install
