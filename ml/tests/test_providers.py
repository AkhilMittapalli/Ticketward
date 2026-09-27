"""Provider client: wire format, retries, key hygiene, config resolution, prices and budget."""

import json
import logging
import random
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.prompts import ChatMessage
from tw_ml.datagen.providers import (
    ApiKey,
    Budget,
    ChatRequest,
    DatagenConfig,
    FakeProvider,
    HttpConfig,
    OpenAICompatibleProvider,
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderSettings,
    RequestConfig,
    TokenUsage,
    UnknownPriceError,
    check_generator_safety,
    load_datagen_config,
    load_price_table,
    resolve_settings,
    safe_error_text,
)

SECRET = "sk-test-DO-NOT-LEAK-1234567890"
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(scope="module")
def config(paths: RepoPaths) -> DatagenConfig:
    return load_datagen_config(paths.configs_dir / "datagen.yaml")


def _settings(family: str = "A") -> ProviderSettings:
    return ProviderSettings(
        family="A" if family == "A" else "B",
        host="deepinfra",
        base_url="https://api.example.test/v1",
        api_model_id="openai/gpt-oss-120b",
        open_weights_model="openai/gpt-oss-120b",
        generator_family="openai_gpt_oss",
        api_key=ApiKey(SECRET),
        http=HttpConfig(
            timeout_s=5,
            connect_timeout_s=1,
            max_retries=2,
            backoff_base_s=0.5,
            backoff_cap_s=4.0,
            retry_after_cap_s=10.0,
        ),
    )


def _provider(handler: Handler, sleeps: list[float]) -> OpenAICompatibleProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        _settings(),
        client=client,
        sleep=sleeps.append,
        rng=random.Random(0),  # noqa: S311 - seeded jitter for a deterministic test, not security
    )


def _request(seed_param: str = "seed") -> ChatRequest:
    params = RequestConfig(
        temperature=1.0,
        top_p=1.0,
        max_tokens=100,
        seed_param=seed_param,  # type: ignore[arg-type]
        extra={"reasoning_effort": "low"},
    )
    messages = (ChatMessage("system", "You write tickets."), ChatMessage("user", "Write one."))
    return ChatRequest(messages=messages, params=params, seed=2**40 + 5, tag="va-c00001:pa")


def _ok(text: str = '{"subject": "x"}', usage: dict[str, object] | None = None) -> httpx.Response:
    body: dict[str, object] = {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]
    }
    body["usage"] = (
        usage
        if usage is not None
        else {
            "prompt_tokens": 120,
            "completion_tokens": 80,
            "completion_tokens_details": {"reasoning_tokens": 30},
        }
    )
    return httpx.Response(200, json=body)


def test_request_wire_format_and_usage() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok()

    result = _provider(handler, []).complete(_request())
    assert result.text == '{"subject": "x"}'
    assert result.usage == TokenUsage(120, 80, 30)
    assert result.attempts == 1
    assert result.finish_reason == "stop"
    request = seen[0]
    assert request.url == "https://api.example.test/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    body = json.loads(request.content)
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["messages"][0] == {"role": "system", "content": "You write tickets."}
    assert body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "low"
    assert body["seed"] == (2**40 + 5) % 2**31
    assert body["top_p"] == 1.0


def test_mistral_uses_random_seed() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _ok()

    _provider(handler, []).complete(_request(seed_param="random_seed"))
    assert "random_seed" in seen[0]
    assert "seed" not in seen[0]


def test_429_is_retried_honouring_retry_after() -> None:
    responses = iter([httpx.Response(429, headers={"Retry-After": "3"}), _ok()])
    sleeps: list[float] = []
    result = _provider(lambda _: next(responses), sleeps).complete(_request())
    assert result.attempts == 2
    assert sleeps
    assert 3.0 <= sleeps[0] <= 10.0


def test_retry_after_http_date_is_capped() -> None:
    later = format_datetime(datetime.now(UTC) + timedelta(hours=1), usegmt=True)
    responses = iter([httpx.Response(503, headers={"Retry-After": later}), _ok()])
    sleeps: list[float] = []
    _provider(lambda _: next(responses), sleeps).complete(_request())
    assert sleeps == [10.0]


def test_server_errors_exhaust_the_bounded_retries() -> None:
    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text=f"internal error for key {SECRET}")

    sleeps: list[float] = []
    with pytest.raises(ProviderError) as caught:
        _provider(handler, sleeps).complete(_request())
    assert len(calls) == 3  # max_retries=2 -> 3 attempts
    assert len(sleeps) == 2
    assert all(0 <= s <= 4.0 for s in sleeps)
    assert caught.value.status == 500
    assert caught.value.retryable
    assert "HTTP 500" in str(caught.value)
    assert SECRET not in str(caught.value)  # the response body is never copied


def test_auth_errors_stop_immediately() -> None:
    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(ProviderAuthError):
        _provider(handler, []).complete(_request())
    assert len(calls) == 1


def test_client_errors_are_not_retried() -> None:
    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": "bad request"})

    with pytest.raises(ProviderError) as caught:
        _provider(handler, []).complete(_request())
    assert len(calls) == 1
    assert not caught.value.retryable


def test_transport_errors_are_retried() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectTimeout("timed out", request=request)
        return _ok()

    sleeps: list[float] = []
    result = _provider(handler, sleeps).complete(_request())
    assert result.attempts == 3
    assert len(sleeps) == 2


def _constant(response: httpx.Response) -> Handler:
    def handler(_: httpx.Request) -> httpx.Response:
        return response

    return handler


def test_malformed_responses_raise() -> None:
    for response in (
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    ):
        with pytest.raises(ProviderError):
            _provider(_constant(response), []).complete(_request())


def test_missing_usage_is_estimated() -> None:
    result = _provider(lambda _: _ok("x" * 70, usage={}), []).complete(_request())
    assert result.usage.estimated
    assert result.usage.output_tokens == 20


def test_api_key_never_appears(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    settings = _settings()
    assert SECRET not in repr(settings)
    assert SECRET not in repr(settings.api_key)
    assert SECRET not in str(settings.api_key)
    with pytest.raises(ProviderError) as caught:
        _provider(lambda _: httpx.Response(503), []).complete(_request())
    assert SECRET not in str(caught.value)
    assert SECRET not in caplog.text
    assert safe_error_text(RuntimeError(f"boom {SECRET}"), [SECRET]) == "RuntimeError: boom ***"
    with pytest.raises(ProviderConfigError):
        ApiKey("   ")


# --------------------------------------------------------------------------- configuration


def test_resolve_settings_defaults_and_overrides(config: DatagenConfig) -> None:
    settings = resolve_settings("A", config, {"TW_DATAGEN_A_API_KEY": SECRET})
    assert (settings.host, settings.base_url) == (
        "deepinfra",
        "https://api.deepinfra.com/v1/openai",
    )
    assert settings.api_model_id == settings.open_weights_model == "openai/gpt-oss-120b"
    fallback = resolve_settings(
        "A", config, {"TW_DATAGEN_A_API_KEY": SECRET, "TW_DATAGEN_A_HOST": "groq"}
    )
    assert fallback.base_url == "https://api.groq.com/openai/v1"
    mistral = resolve_settings("B", config, {"TW_DATAGEN_B_API_KEY": SECRET})
    assert mistral.api_model_id == "mistral-large-3-25-12"
    assert mistral.open_weights_model == "mistralai/Mistral-Large-3-675B-Instruct-2512"
    custom = resolve_settings(
        "A",
        config,
        {
            "TW_DATAGEN_A_API_KEY": SECRET,
            "TW_DATAGEN_A_BASE_URL": "http://localhost:8000/v1/",
            "TW_DATAGEN_A_MODEL": "openai/gpt-oss-120b",
        },
    )
    assert custom.base_url == "http://localhost:8000/v1"


def test_resolve_settings_refuses_unsafe_or_incomplete_setups(config: DatagenConfig) -> None:
    with pytest.raises(ProviderConfigError, match="TW_DATAGEN_A_API_KEY"):
        resolve_settings("A", config, {})
    with pytest.raises(ProviderConfigError, match="unknown host"):
        resolve_settings("A", config, {"TW_DATAGEN_A_API_KEY": SECRET}, host="nowhere")
    env = {"TW_DATAGEN_A_API_KEY": SECRET, "TW_DATAGEN_A_BASE_URL": "http://api.remote.test/v1"}
    with pytest.raises(ProviderConfigError, match="https"):
        resolve_settings("A", config, env)
    family = config.families["A"]
    with pytest.raises(ProviderConfigError, match="Anthropic"):
        check_generator_safety("https://api.anthropic.com/v1", "gpt-oss-120b", family)
    with pytest.raises(ProviderConfigError, match="Anthropic"):
        check_generator_safety("https://host.test/v1", "claude-gpt-oss-120b", family)
    with pytest.raises(ProviderConfigError, match="generator"):
        check_generator_safety("https://host.test/v1", "mistral-large-3-25-12", family)


def test_config_files_load(paths: RepoPaths, config: DatagenConfig, tmp_path: Path) -> None:
    assert config.terms_snapshot_id == "docs/legal/generator-terms-2026-09-27.md"
    assert config.budget_usd_total == Decimal("15.00")
    assert (paths.root / config.terms_snapshot_id).is_file()
    bad = tmp_path / "datagen.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(ProviderConfigError, match="malformed"):
        load_datagen_config(bad)
    with pytest.raises(ProviderConfigError, match="malformed"):
        load_price_table(bad)


# --------------------------------------------------------------------------- prices and budget


def test_price_table_costs(paths: RepoPaths) -> None:
    prices = load_price_table(paths.configs_dir / "datagen_prices.v1.yaml")
    assert prices.as_of.isoformat() == "2026-09-27"
    cost = prices.cost(TokenUsage(1_000_000, 1_000_000), "deepinfra", "openai/gpt-oss-120b")
    assert cost == Decimal("0.207")
    assert prices.cost(TokenUsage(2_000_000, 0), "mistral", "mistral-large-3-25-12") == Decimal(
        "1.00"
    )
    estimate = prices.estimate(3500, 1000, "groq", "openai/gpt-oss-120b")
    assert estimate == Decimal("0.00075")  # 1000 input (3500/3.5) + 1000 output tokens
    with pytest.raises(UnknownPriceError):
        prices.entry("somehost", "some-model")


def test_budget_enforces_run_and_total_caps() -> None:
    budget = Budget(
        run_cap=Decimal("1.00"), total_cap=Decimal("15.00"), spent_before=Decimal("14.50")
    )
    assert budget.allows(Decimal("0.50"))
    assert not budget.allows(Decimal("0.51"))  # total cap
    budget.charge(Decimal("0.40"))
    assert budget.spent_run == Decimal("0.40")
    capped = Budget(run_cap=Decimal("0.10"), total_cap=Decimal("15"))
    assert not capped.allows(Decimal("0.11"))  # run cap


def test_fake_provider_is_deterministic_and_can_fail() -> None:
    fake = FakeProvider(lambda request: request.tag.upper())
    failure = ProviderError("queued failure", retryable=True)
    fake.failures.append(failure)
    with pytest.raises(ProviderError, match="queued"):
        fake.complete(_request())
    result = fake.complete(_request())
    assert result.text == "VA-C00001:PA"
    assert result.usage.output_tokens == 3
    assert len(fake.calls) == 2


def test_only_the_provider_module_builds_http_clients(paths: RepoPaths) -> None:
    # ml analogue of the backend's T-NO-SEND rule: one outbound HTTP construction site.
    pattern = re.compile(r"httpx\.(?:Async)?Client\(|urllib\.request|import requests|http\.client")
    offenders = [
        path.name
        for path in sorted((paths.root / "ml" / "src").rglob("*.py"))
        if pattern.search(path.read_text(encoding="utf-8")) and path.name != "providers.py"
    ]
    assert offenders == []
