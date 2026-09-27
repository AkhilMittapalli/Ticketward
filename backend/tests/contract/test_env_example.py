"""`.env.example` documents every setting, holds no secrets and is itself valid."""

import re
from pathlib import Path

import pytest

from ticketward.core.config import SECRETS_DIR_ENV, Environment, Settings

ASSIGNMENT = re.compile(r"^(#\s*)?(TW_[A-Z0-9_]+)=(.*)$", re.MULTILINE)
SECRET_NAMES = {"TW_DB_PASSWORD", "TW_REDIS_PASSWORD", "TW_TEST_REDIS_PASSWORD"}


def _entries(repo_root: Path) -> list[tuple[bool, str, str]]:
    text = (repo_root / ".env.example").read_text(encoding="utf-8")
    return [(bool(commented), name, value) for commented, name, value in ASSIGNMENT.findall(text)]


def test_every_setting_is_documented(repo_root: Path) -> None:
    documented = {name for _, name, _ in _entries(repo_root)}
    expected = {f"TW_{field.upper()}" for field in Settings.model_fields} | {SECRETS_DIR_ENV}
    assert expected - documented == set()


def test_no_secret_values_are_committed(repo_root: Path) -> None:
    for commented, name, value in _entries(repo_root):
        if name in SECRET_NAMES or "PASSWORD" in name:
            assert commented, f"{name} must stay commented out (use secret files)"
            assert value.startswith("<placeholder"), name
        assert "hunter2" not in value


def test_example_values_are_valid_settings(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for commented, name, value in _entries(repo_root):
        if not commented and name != SECRETS_DIR_ENV:
            monkeypatch.setenv(name, value)
    settings = Settings(_secrets_dir=None)
    assert settings.env is Environment.dev
    assert settings.docs_enabled is None
    assert settings.cors_origins == ["http://localhost:3000"]
