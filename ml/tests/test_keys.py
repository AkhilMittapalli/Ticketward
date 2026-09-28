"""Generator API keys in the OS credential store (tw_ml.datagen.keys) and the ``keys`` CLI.

The autouse ``_hermetic_environment`` fixture swaps in an in-memory store, so nothing here
touches the developer's real credential store.
"""

import getpass
import re

import keyring
import keyring.backends.null
import pytest

from tw_ml.datagen import keys
from tw_ml.datagen.__main__ import main
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.providers import (
    DatagenConfig,
    ProviderConfigError,
    load_datagen_config,
    resolve_settings,
)

FAKE_KEY = "fake-key-value-aaaaaaaaaaaaaaaa"
OTHER_KEY = "other-fake-key-bbbbbbbbbbbbbbbb"


@pytest.fixture(scope="module")
def config(paths: RepoPaths) -> DatagenConfig:
    return load_datagen_config(paths.configs_dir / "datagen.yaml")


def test_validate_key_strips_and_rejects_bad_input() -> None:
    assert keys.validate_key(f"  {FAKE_KEY}\n") == FAKE_KEY
    for bad in ("", "   ", "has inner whitespace-aaaaaaaaaaaa", "short", "x" * 600):
        with pytest.raises(keys.KeyStoreError) as excinfo:
            keys.validate_key(bad)
        if bad.strip():
            assert bad.strip() not in str(excinfo.value)


def test_store_load_delete_round_trip() -> None:
    assert keys.load_key("A", "deepinfra") is None
    keys.store_key("A", "deepinfra", FAKE_KEY)
    assert keys.load_key("A", "deepinfra") == FAKE_KEY
    assert keyring.get_password(keys.SERVICE, "A:deepinfra") == FAKE_KEY
    assert keys.load_key("A", "groq") is None
    assert keys.delete_key("A", "deepinfra") is True
    assert keys.delete_key("A", "deepinfra") is False
    assert keys.load_key("A", "deepinfra") is None


def test_insecure_backend_is_refused() -> None:
    keyring.set_keyring(keyring.backends.null.Keyring())  # type: ignore[no-untyped-call]
    assert any(name.startswith("keyring.backends.null.") for name in keys.backend_names())
    with pytest.raises(keys.KeyStoreError, match="no secure credential store"):
        keys.store_key("A", "deepinfra", FAKE_KEY)
    with pytest.raises(keys.KeyStoreError):
        keys.delete_key("A", "deepinfra")
    assert keys.load_key("A", "deepinfra") is None


def test_environment_key_wins_over_stored_key(config: DatagenConfig) -> None:
    keys.store_key("A", "deepinfra", OTHER_KEY)
    settings = resolve_settings(
        "A", config, {"TW_DATAGEN_A_API_KEY": FAKE_KEY}, key_lookup=keys.load_key
    )
    assert settings.api_key.reveal() == FAKE_KEY


def test_stored_key_is_used_when_environment_has_none(config: DatagenConfig) -> None:
    keys.store_key("A", "groq", FAKE_KEY)
    settings = resolve_settings("A", config, {}, host="groq", key_lookup=keys.load_key)
    assert (settings.host, settings.api_key.reveal()) == ("groq", FAKE_KEY)


def test_missing_key_points_to_keys_set(config: DatagenConfig) -> None:
    with pytest.raises(ProviderConfigError) as excinfo:
        resolve_settings("B", config, {}, key_lookup=keys.load_key)
    message = str(excinfo.value)
    assert "keys set --family B --host deepinfra" in message
    assert "TW_DATAGEN_B_API_KEY" in message


def test_a_family_reuses_another_familys_key_on_the_same_host_only() -> None:
    """D-07: one DeepInfra account serves A and B, so B:deepinfra falls back to A:deepinfra."""
    keys.store_key("A", "deepinfra", FAKE_KEY)
    assert keys.load_key("B", "deepinfra") == FAKE_KEY
    assert keys.find_key("B", "deepinfra") == (FAKE_KEY, "A:deepinfra")
    assert keys.key_status("B", "deepinfra") == "stored (shared with A:deepinfra)"
    assert keys.key_status("A", "deepinfra") == "stored"
    assert keys.load_key("B", "groq") is None  # keys never cross hosts
    assert keys.key_status("B", "groq") == "not stored"
    keys.store_key("B", "deepinfra", OTHER_KEY)  # a family's own key always wins
    assert keys.find_key("B", "deepinfra") == (OTHER_KEY, "B:deepinfra")
    assert keys.load_key("A", "deepinfra") == FAKE_KEY
    assert keys.delete_key("B", "deepinfra") is True
    assert keys.load_key("B", "deepinfra") == FAKE_KEY


def test_family_b_resolves_with_the_shared_deepinfra_key(config: DatagenConfig) -> None:
    keys.store_key("A", "deepinfra", FAKE_KEY)
    settings = resolve_settings("B", config, {}, key_lookup=keys.load_key)
    assert (settings.host, settings.api_model_id) == ("deepinfra", "deepseek-ai/DeepSeek-V3.2")
    assert settings.api_key.reveal() == FAKE_KEY


def test_status_shows_shared_keys_and_delete_keeps_them(
    capsys: pytest.CaptureFixture[str], paths: RepoPaths
) -> None:
    keys.store_key("A", "deepinfra", FAKE_KEY)
    assert main(["keys", "status"], paths) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    shared = r"\s+B:deepinfra\s+stored \(shared with A:deepinfra\)"
    assert any(re.fullmatch(shared, line) for line in lines)
    assert any(re.fullmatch(r"\s+A:groq\s+not stored", line) for line in lines)
    assert FAKE_KEY not in out
    assert main(["keys", "delete", "--family", "B"], paths) == 0
    assert "nothing stored for B:deepinfra" in capsys.readouterr().out
    assert keys.load_key("A", "deepinfra") == FAKE_KEY


def test_cli_set_status_delete_never_prints_the_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], paths: RepoPaths
) -> None:
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": FAKE_KEY)
    assert main(["keys", "set", "--family", "A"], paths) == 0
    assert keys.load_key("A", "deepinfra") == FAKE_KEY
    assert main(["keys", "status"], paths) == 0
    out = capsys.readouterr().out
    assert "A:deepinfra" in out
    assert "stored" in out
    assert FAKE_KEY not in out

    assert main(["keys", "delete", "--family", "A"], paths) == 0
    assert keys.load_key("A", "deepinfra") is None
    assert main(["keys", "delete", "--family", "A"], paths) == 0
    assert "nothing stored for A:deepinfra" in capsys.readouterr().out


def test_cli_rejects_unknown_host_and_malformed_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], paths: RepoPaths
) -> None:
    assert main(["keys", "set", "--family", "A", "--host", "nope"], paths) == 2
    assert "unknown host" in capsys.readouterr().err
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "not a key")
    assert main(["keys", "set", "--family", "A"], paths) == 2
    err = capsys.readouterr().err
    assert "whitespace" in err
    assert "not a key" not in err
    assert keys.load_key("A", "deepinfra") is None


def test_status_flags_environment_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], paths: RepoPaths
) -> None:
    monkeypatch.setenv("TW_DATAGEN_A_API_KEY", FAKE_KEY)
    assert main(["keys", "status"], paths) == 0
    out = capsys.readouterr().out
    assert "overridden by the environment variable" in out
    assert FAKE_KEY not in out


def test_stored_keys_never_follow_an_overridden_base_url(config: DatagenConfig) -> None:
    keys.store_key("A", "deepinfra", FAKE_KEY)
    for family in ("A", "B"):
        env = {f"TW_DATAGEN_{family}_BASE_URL": "https://elsewhere.example.test/v1"}
        with pytest.raises(ProviderConfigError, match="sent only to their host") as excinfo:
            resolve_settings(family, config, env, key_lookup=keys.load_key)
        assert FAKE_KEY not in str(excinfo.value)
    same = {"TW_DATAGEN_B_BASE_URL": "https://api.deepinfra.com/v1/openai/"}  # same URL
    settings = resolve_settings("B", config, same, key_lookup=keys.load_key)
    assert settings.api_key.reveal() == FAKE_KEY
