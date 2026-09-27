from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from ticketward.core.config import (
    MIN_PROD_SECRET_LENGTH,
    Environment,
    Settings,
    get_settings,
    resolve_secrets_dir,
    secret_problem,
)

STRONG_DB_PASSWORD = "Zq8vN2kLr5TtY7wPx3Hm"
STRONG_REDIS_PASSWORD = "a9F3kQ7mZ2xW8vB4nR6t"


def load(secrets_dir: Path | None = None, **values: Any) -> Settings:
    """Build settings from explicit values (env vars still apply; tests isolate them)."""
    return Settings(_secrets_dir=secrets_dir, **values)


def prod_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "env": "prod",
        "db_password": STRONG_DB_PASSWORD,
        "redis_password": STRONG_REDIS_PASSWORD,
    }
    values.update(overrides)
    return load(**values)


def test_unconfigured_environment_fails_closed_to_prod() -> None:
    with pytest.raises(ValidationError, match="refusing to start in prod"):
        Settings(_secrets_dir=None)


def test_test_environment_needs_no_secrets() -> None:
    settings = load(env="test")
    assert settings.env is Environment.test
    assert settings.db_password is None
    assert settings.body_limit_default_bytes == 65_536
    assert settings.frontier_enabled is False


def test_prod_accepts_strong_configuration() -> None:
    settings = prod_settings()
    assert settings.env is Environment.prod
    assert settings.openapi_enabled is False
    assert settings.debug is False


def test_prod_refuses_missing_secrets_and_names_them() -> None:
    with pytest.raises(ValidationError) as excinfo:
        load(env="prod")
    message = str(excinfo.value)
    assert "the database password is not set" in message
    assert "TW_REDIS_PASSWORD is not set" in message


@pytest.mark.parametrize(
    "value",
    [
        "CHANGE_ME_generate_with_openssl",
        "placeholder-placeholder-1234",
        "an-example-value-that-is-long",
        "my-default-password-123456",
    ],
)
def test_prod_refuses_placeholder_secrets(value: str) -> None:
    with pytest.raises(ValidationError, match="looks like a placeholder"):
        prod_settings(db_password=value)


def test_prod_refuses_short_secret() -> None:
    with pytest.raises(ValidationError, match=f"shorter than {MIN_PROD_SECRET_LENGTH}"):
        prod_settings(redis_password="Sh0rt!")


def test_prod_error_never_echoes_secret_values() -> None:
    leaked = "placeholder-" + "Q" * 20
    with pytest.raises(ValidationError) as excinfo:
        prod_settings(db_password=leaked)
    assert leaked not in str(excinfo.value)
    assert leaked not in repr(excinfo.value)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"debug": True}, "TW_DEBUG must be false"),
        ({"docs_enabled": True}, "TW_DOCS_ENABLED must be false"),
        ({"log_json": False}, "TW_LOG_JSON must be true"),
        ({"cors_origins": ["https://app.example.test"]}, "TW_CORS_ORIGINS must be empty"),
    ],
)
def test_prod_refuses_insecure_flags(overrides: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        prod_settings(**overrides)


def test_prod_checks_password_inside_database_url() -> None:
    with pytest.raises(ValidationError, match="the database password is not set"):
        prod_settings(database_url="postgresql+asyncpg://rf@db:5432/rf")
    settings = prod_settings(
        database_url=f"postgresql+asyncpg://rf:{STRONG_DB_PASSWORD}@db:5432/rf", db_password=None
    )
    assert settings.database_url is not None


def test_database_url_is_secret_and_requires_asyncpg() -> None:
    settings = load(env="test", database_url="postgresql+asyncpg://u:pw@h:5432/d")
    assert isinstance(settings.database_url, SecretStr)
    assert "pw" not in repr(settings)
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        load(env="test", database_url="postgresql://u:pw@h/d")


@pytest.mark.parametrize(
    ("url", "fragment"),
    [
        ("http://localhost:6379/0", "redis:// or rediss://"),
        ("redis:///0", "redis:// or rediss://"),
        ("redis://:hunter2@localhost:6379/0", "must not embed credentials"),
        ("rediss://user:pw@cache:6380/0", "must not embed credentials"),
    ],
)
def test_redis_url_validation(url: str, fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        load(env="test", redis_url=url)


def test_rediss_url_accepted() -> None:
    settings = load(env="test", redis_url="rediss://cache:6380/1")
    assert settings.redis_url == "rediss://cache:6380/1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("http://localhost:3000", ["http://localhost:3000"]),
        (
            "http://localhost:3000/, https://ui.example.test",
            ["http://localhost:3000", "https://ui.example.test"],
        ),
        ('["http://127.0.0.1:3000"]', ["http://127.0.0.1:3000"]),
    ],
)
def test_cors_origins_parsing_from_env(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("TW_ENV", "dev")
    monkeypatch.setenv("TW_CORS_ORIGINS", raw)
    assert Settings(_secrets_dir=None).cors_origins == expected


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.test",
        "ftp://files.example.test",
        "https://ui.example.test/app",
        "https://user@ui.example.test",
        "localhost:3000",
    ],
)
def test_cors_origins_rejects_unsafe_values(origin: str) -> None:
    with pytest.raises(ValidationError):
        load(env="dev", cors_origins=[origin])


@pytest.mark.parametrize("raw", ["", "   ", " , ,"])
def test_blank_cors_values_mean_no_origins(raw: str) -> None:
    assert load(env="dev", cors_origins=raw).cors_origins == []


def test_empty_environment_values_are_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TW_ENV", "dev")
    monkeypatch.setenv("TW_DOCS_ENABLED", "")
    monkeypatch.setenv("TW_BODY_LIMIT_DEFAULT_BYTES", "")
    settings = Settings(_secrets_dir=None)
    assert settings.docs_enabled is None
    assert settings.body_limit_default_bytes == 65_536


def test_environment_variables_are_read_with_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TW_ENV", "dev")
    monkeypatch.setenv("TW_BODY_LIMIT_TICKET_BYTES", "4096")
    monkeypatch.setenv("TW_FRONTIER_ENABLED", "true")
    settings = Settings(_secrets_dir=None)
    assert settings.env is Environment.dev
    assert settings.body_limit_ticket_bytes == 4096
    assert settings.frontier_enabled is True


def test_secret_files_are_loaded_and_stripped(tmp_path: Path) -> None:
    (tmp_path / "tw_db_password").write_text(STRONG_DB_PASSWORD + "\n", encoding="utf-8")
    (tmp_path / "tw_redis_password").write_text(STRONG_REDIS_PASSWORD, encoding="utf-8")
    settings = load(tmp_path, env="prod")
    assert settings.db_password is not None
    assert settings.db_password.get_secret_value() == STRONG_DB_PASSWORD
    assert settings.redis_password is not None
    assert settings.redis_password.get_secret_value() == STRONG_REDIS_PASSWORD


def test_get_settings_reads_secrets_dir_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "tw_db_password").write_text(STRONG_DB_PASSWORD, encoding="utf-8")
    monkeypatch.setenv("TW_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("TW_ENV", "test")
    assert resolve_secrets_dir() == tmp_path
    settings = get_settings()
    assert settings.db_password is not None
    assert settings.db_password.get_secret_value() == STRONG_DB_PASSWORD


def test_missing_secrets_dir_is_ignored_without_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TW_SECRETS_DIR", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("TW_ENV", "test")
    assert resolve_secrets_dir() is None
    assert get_settings().env is Environment.test


@pytest.mark.parametrize(
    ("env", "docs_enabled", "expected"),
    [
        ("dev", None, True),
        ("test", None, True),
        ("prod", None, False),
        ("dev", False, False),
        ("dev", True, True),
        ("prod", False, False),
    ],
)
def test_openapi_enabled_resolution(env: str, docs_enabled: bool | None, expected: bool) -> None:
    make: Callable[..., Settings] = prod_settings if env == "prod" else load
    settings = make(env=env, docs_enabled=docs_enabled)
    assert settings.openapi_enabled is expected


def test_settings_are_immutable() -> None:
    settings = load(env="test")
    with pytest.raises(ValidationError):
        settings.debug = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "is not set"),
        ("   ", "is not set"),
        ("short", "is shorter than"),
        ("TODO-set-a-real-value-here", "placeholder"),
        (STRONG_DB_PASSWORD, None),
    ],
)
def test_secret_problem(value: str | None, reason: str | None) -> None:
    problem = secret_problem(value)
    if reason is None:
        assert problem is None
    else:
        assert problem is not None
        assert reason in problem
