"""Generator providers: one OpenAI-compatible chat-completions client for every host.

Family A (``openai/gpt-oss-120b``, train/val) runs on DeepInfra by default with Groq as the
fallback; Family B (Mistral Large 3, test_synth) runs on Mistral La Plateforme (spec v1.1 A-01;
``docs/legal/generator-terms-2026-09-27.md``). All three speak the OpenAI chat-completions wire
format, so one small ``httpx`` client covers them; host differences (the seed parameter name,
``reasoning_effort``) are configuration.

Configuration comes from ``ml/configs/datagen.yaml`` and is overridden by environment variables
``TW_DATAGEN_{A,B}_HOST``, ``_BASE_URL``, ``_MODEL`` and ``_API_KEY``. The API key lives only in
an :class:`ApiKey`, whose ``repr``/``str`` are redacted; it is sent in one header and never
appears in logs, exceptions or files. Response bodies are never copied into error messages.

This module is the only place in ``tw_ml`` that constructs an HTTP client (the ml analogue of
the backend's T-NO-SEND rule; ``tests/test_providers.py`` enforces it).
"""

import math
import random
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Final, Literal, Protocol
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tw_ml.datagen.prompts import ChatMessage

Family = Literal["A", "B"]
ENV_PREFIXES: Final[Mapping[Family, str]] = {"A": "TW_DATAGEN_A_", "B": "TW_DATAGEN_B_"}
RETRYABLE_STATUS: Final[frozenset[int]] = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
AUTH_STATUS: Final[frozenset[int]] = frozenset({401, 403})
LOCAL_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
FORBIDDEN_GENERATOR: Final = re.compile(r"anthropic|claude", re.IGNORECASE)
CHARS_PER_TOKEN_ESTIMATE: Final = 3.5  # conservative (overestimates tokens) for budget checks
MILLION: Final = Decimal(1_000_000)
USER_AGENT: Final = "tw-ml-datagen/0.1"


class ProviderError(RuntimeError):
    """A provider call failed; the message never contains the key or a response body."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        """Create the error.

        Args:
            message: Safe, content-free description.
            status: HTTP status when one was received.
            retryable: Whether retrying could succeed.
        """
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class ProviderAuthError(ProviderError):
    """The host rejected the credentials (HTTP 401/403); a run must stop."""


class ProviderConfigError(ValueError):
    """The provider configuration or environment is incomplete or unsafe."""


class UnknownPriceError(KeyError):
    """No dated price exists for a host/model pair, so the budget cannot be enforced."""


class ApiKey:
    """An API key that never prints itself."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        """Wrap a key.

        Args:
            value: The secret.

        Raises:
            ProviderConfigError: If the key is empty.
        """
        if not value.strip():
            msg = "API key is empty"
            raise ProviderConfigError(msg)
        self._value = value.strip()

    def reveal(self) -> str:
        """Return the secret (only for the Authorization header).

        Returns:
            The key.
        """
        return self._value

    def __repr__(self) -> str:
        return "ApiKey('***')"

    __str__ = __repr__


# --------------------------------------------------------------------------- config


class ConfigModel(BaseModel):
    """Strict base for the datagen config models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class HttpConfig(ConfigModel):
    """Timeouts and retry policy."""

    timeout_s: float = Field(gt=0)
    connect_timeout_s: float = Field(gt=0)
    max_retries: int = Field(ge=0, le=10)
    backoff_base_s: float = Field(gt=0)
    backoff_cap_s: float = Field(gt=0)
    retry_after_cap_s: float = Field(gt=0)


class RequestConfig(ConfigModel):
    """Sampling parameters of one request type."""

    temperature: float = Field(ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_tokens: int = Field(gt=0)
    response_format: Literal["json_object"] | None = "json_object"
    seed_param: Literal["seed", "random_seed"] | None = "seed"
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)


class HostConfig(ConfigModel):
    """One host serving a family's model."""

    base_url: str
    api_model_id: str


class FamilyConfig(ConfigModel):
    """One generator family."""

    generator_family: Literal["openai_gpt_oss", "mistral"]
    open_weights_model: str
    allowed_model_patterns: tuple[str, ...] = Field(min_length=1)
    default_host: str
    hosts: dict[str, HostConfig]
    requests: dict[str, RequestConfig]


class DatagenConfig(ConfigModel):
    """``ml/configs/datagen.yaml``."""

    version: str
    terms_snapshot_id: str
    terms_max_age_days: int = Field(gt=0)
    price_table: str
    budget_usd_total: Decimal = Field(gt=0)
    max_attempts_per_cell: int = Field(ge=1, le=5)
    http: HttpConfig
    families: dict[Family, FamilyConfig]


def load_datagen_config(path: Path) -> DatagenConfig:
    """Load the datagen config.

    Args:
        path: ``ml/configs/datagen.yaml``.

    Returns:
        The validated config.

    Raises:
        ProviderConfigError: If the file is malformed.
    """
    try:
        return DatagenConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        msg = f"{path.name} is malformed: {exc.error_count()} validation error(s)"
        raise ProviderConfigError(msg) from exc


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    """Resolved settings of one provider (config + environment).

    Attributes:
        family: Generator family (A or B).
        host: Host label (``deepinfra``, ``groq``, ``mistral``); the provenance ``provider``.
        base_url: OpenAI-compatible base URL.
        api_model_id: The host's model id.
        open_weights_model: The open-weights id recorded as ``generator_model``.
        generator_family: Provenance family value.
        api_key: The key (redacted when printed).
        http: Timeouts and retry policy.
    """

    family: Family
    host: str
    base_url: str
    api_model_id: str
    open_weights_model: str
    generator_family: str
    api_key: ApiKey = field(repr=False)
    http: HttpConfig


def resolve_settings(
    family: Family,
    config: DatagenConfig,
    env: Mapping[str, str],
    host: str | None = None,
) -> ProviderSettings:
    """Combine config defaults with ``TW_DATAGEN_<family>_*`` environment overrides.

    Args:
        family: A or B.
        config: Datagen config.
        env: Environment mapping (``os.environ`` in the CLI).
        host: Host label override (e.g. ``groq`` for the Family A fallback).

    Returns:
        The resolved settings.

    Raises:
        ProviderConfigError: If the key is missing, the URL is unsafe, the host is unknown or the
            model is not the family's generator.
    """
    prefix = ENV_PREFIXES[family]
    family_config = config.families[family]
    label = host or env.get(f"{prefix}HOST") or family_config.default_host
    host_config = family_config.hosts.get(label)
    base_url = env.get(f"{prefix}BASE_URL") or (host_config.base_url if host_config else "")
    model = env.get(f"{prefix}MODEL") or (host_config.api_model_id if host_config else "")
    if not base_url or not model:
        msg = f"unknown host {label!r}; set {prefix}BASE_URL and {prefix}MODEL"
        raise ProviderConfigError(msg)
    key = env.get(f"{prefix}API_KEY", "")
    if not key.strip():
        msg = f"{prefix}API_KEY is not set"
        raise ProviderConfigError(msg)
    check_generator_safety(base_url, model, family_config)
    return ProviderSettings(
        family=family,
        host=label,
        base_url=base_url.rstrip("/"),
        api_model_id=model,
        open_weights_model=family_config.open_weights_model,
        generator_family=family_config.generator_family,
        api_key=ApiKey(key),
        http=config.http,
    )


def check_generator_safety(base_url: str, model: str, family_config: FamilyConfig) -> None:
    """Refuse unsafe endpoints and wrong generators (A-01: never Claude for any data).

    Args:
        base_url: Endpoint base URL.
        model: The host's model id.
        family_config: Family config (allowed model patterns).

    Raises:
        ProviderConfigError: On a non-HTTPS remote URL, an Anthropic endpoint or model, or a
            model outside the family's allowed patterns.
    """
    parts = urlsplit(base_url)
    local = (parts.hostname or "") in LOCAL_HOSTS
    if parts.scheme != "https" and not (local and parts.scheme == "http"):
        msg = "generator base URL must use https (http only for localhost)"
        raise ProviderConfigError(msg)
    if FORBIDDEN_GENERATOR.search(base_url) or FORBIDDEN_GENERATOR.search(model):
        msg = "Anthropic models and endpoints must never generate data (A-01)"
        raise ProviderConfigError(msg)
    if not any(p.lower() in model.lower() for p in family_config.allowed_model_patterns):
        msg = f"model {model!r} is not this family's generator"
        raise ProviderConfigError(msg)


# --------------------------------------------------------------------------- prices and budget


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token counts of one call.

    Attributes:
        input_tokens: Prompt tokens.
        output_tokens: Completion tokens (reasoning included, as billed).
        reasoning_tokens: Reasoning tokens reported inside the completion, if any.
        estimated: True when the host returned no usage and counts were estimated.
    """

    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0
    estimated: bool = False


class PriceEntry(ConfigModel):
    """Dated per-million-token prices of one host/model pair."""

    provider: str
    api_model_id: str
    input_per_mtok: Decimal = Field(ge=0)
    output_per_mtok: Decimal = Field(ge=0)


class PriceTable(ConfigModel):
    """``ml/configs/datagen_prices.v1.yaml``."""

    version: str
    as_of: date
    currency: Literal["USD"]
    unit: Literal["per_million_tokens"]
    source: str
    entries: tuple[PriceEntry, ...]

    def entry(self, provider: str, api_model_id: str) -> PriceEntry:
        """Look up a price.

        Args:
            provider: Host label.
            api_model_id: The host's model id.

        Returns:
            The price entry.

        Raises:
            UnknownPriceError: If the pair is not priced.
        """
        for item in self.entries:
            if item.provider == provider and item.api_model_id == api_model_id:
                return item
        raise UnknownPriceError(f"{provider}/{api_model_id}")

    def cost(self, usage: TokenUsage, provider: str, api_model_id: str) -> Decimal:
        """Cost of one call (reasoning tokens are billed inside the output tokens).

        Args:
            usage: Token counts.
            provider: Host label.
            api_model_id: The host's model id.

        Returns:
            USD cost.
        """
        price = self.entry(provider, api_model_id)
        cost = (
            usage.input_tokens * price.input_per_mtok + usage.output_tokens * price.output_per_mtok
        )
        return cost / MILLION

    def estimate(
        self, prompt_chars: int, max_tokens: int, provider: str, api_model_id: str
    ) -> Decimal:
        """Conservative pre-call cost bound (all ``max_tokens`` spent, rounded-up input).

        Args:
            prompt_chars: Characters of all prompt messages.
            max_tokens: Output token cap of the request.
            provider: Host label.
            api_model_id: The host's model id.

        Returns:
            USD upper estimate.
        """
        usage = TokenUsage(math.ceil(prompt_chars / CHARS_PER_TOKEN_ESTIMATE), max_tokens)
        return self.cost(usage, provider, api_model_id)


def load_price_table(path: Path) -> PriceTable:
    """Load the dated price table.

    Args:
        path: Price table file.

    Returns:
        The validated table.

    Raises:
        ProviderConfigError: If the file is malformed.
    """
    try:
        return PriceTable.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        msg = f"{path.name} is malformed: {exc.error_count()} validation error(s)"
        raise ProviderConfigError(msg) from exc


@dataclass(slots=True)
class Budget:
    """Spend caps for one run and for all generation so far (the $15 budget).

    Attributes:
        run_cap: Cap for this run (``--budget-usd``).
        total_cap: Cap across every ledger under ``data/generated``.
        spent_before: Spend recorded before this run started.
        spent_run: Spend recorded by this run.
    """

    run_cap: Decimal
    total_cap: Decimal
    spent_before: Decimal = Decimal(0)
    spent_run: Decimal = Decimal(0)

    def allows(self, estimate: Decimal) -> bool:
        """Return whether a call with this cost estimate stays inside both caps.

        Args:
            estimate: Upper cost estimate of the next call.

        Returns:
            True when the call may be made.
        """
        after = self.spent_run + estimate
        return after <= self.run_cap and self.spent_before + after <= self.total_cap

    def charge(self, cost: Decimal) -> None:
        """Record an actual cost.

        Args:
            cost: USD cost of a completed call.
        """
        self.spent_run += cost


# --------------------------------------------------------------------------- requests


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """One chat-completion request.

    Attributes:
        messages: Rendered prompt messages.
        params: Sampling parameters.
        seed: Deterministic seed (sent under the host's seed parameter name).
        tag: Opaque label for fakes and ledgers (e.g. ``cell_id:stage``); never sent.
    """

    messages: tuple[ChatMessage, ...]
    params: RequestConfig
    seed: int | None = None
    tag: str = ""

    def prompt_chars(self) -> int:
        """Total prompt size in characters.

        Returns:
            Sum of message lengths.
        """
        return sum(len(m.content) for m in self.messages)


@dataclass(frozen=True, slots=True)
class ChatResult:
    """A successful completion.

    Attributes:
        text: Message content returned by the model.
        usage: Token counts.
        finish_reason: Host-reported finish reason.
        attempts: HTTP attempts used (1 = no retry).
        latency_ms: Wall time of the final attempt.
    """

    text: str
    usage: TokenUsage
    finish_reason: str | None
    attempts: int
    latency_ms: int


class ChatProvider(Protocol):
    """What the generation loop needs from a provider."""

    @property
    def host(self) -> str:
        """Host label (provenance ``provider``)."""
        ...

    @property
    def api_model_id(self) -> str:
        """The host's model id."""
        ...

    @property
    def open_weights_model(self) -> str:
        """Open-weights model id (provenance ``generator_model``)."""
        ...

    def complete(self, request: ChatRequest) -> ChatResult:
        """Run one completion."""
        ...


class OpenAICompatibleProvider:
    """Chat-completions client for any OpenAI-compatible host (DeepInfra, Groq, Mistral...)."""

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        """Create the provider.

        Args:
            settings: Resolved settings.
            client: Injected HTTP client (tests use ``httpx.MockTransport``).
            sleep: Sleep function used between retries (injectable for tests).
            rng: Jitter source (injectable for deterministic tests).
        """
        self._settings = settings
        timeout = httpx.Timeout(settings.http.timeout_s, connect=settings.http.connect_timeout_s)
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False)
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311 - jitter only

    @property
    def host(self) -> str:
        """Host label (provenance ``provider``)."""
        return self._settings.host

    @property
    def api_model_id(self) -> str:
        """The host's model id."""
        return self._settings.api_model_id

    @property
    def open_weights_model(self) -> str:
        """Open-weights model id (provenance ``generator_model``)."""
        return self._settings.open_weights_model

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def complete(self, request: ChatRequest) -> ChatResult:
        """Run one completion with bounded, jittered retries on 429/5xx and transport errors.

        Args:
            request: The request.

        Returns:
            The completion.

        Raises:
            ProviderAuthError: On HTTP 401/403 (no retry).
            ProviderError: On other non-retryable statuses, malformed responses, or when the
                retries are exhausted.
        """
        http = self._settings.http
        url = f"{self._settings.base_url}/chat/completions"
        body = self._body(request)
        headers = {
            "Authorization": f"Bearer {self._settings.api_key.reveal()}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        attempts = http.max_retries + 1
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            retry_after: float | None = None
            try:
                response = self._client.post(url, json=body, headers=headers)
            except httpx.TransportError as exc:  # timeouts are TransportErrors too
                failure = ProviderError(
                    f"{self.host}: transport error {type(exc).__name__} "
                    f"(attempt {attempt}/{attempts})",
                    retryable=True,
                )
            else:
                status = response.status_code
                if status < httpx.codes.BAD_REQUEST:
                    latency = int((time.monotonic() - started) * 1000)
                    return self._parse(response, attempt, latency)
                failure = self._status_error(status, attempt, attempts)
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            if not failure.retryable or attempt == attempts:
                raise failure
            self._sleep(self._delay(attempt, retry_after))
        msg = f"{self.host}: retries exhausted"  # unreachable: the loop returns or raises
        raise ProviderError(msg)

    def _body(self, request: ChatRequest) -> dict[str, Any]:
        params = request.params
        body: dict[str, Any] = {
            "model": self._settings.api_model_id,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.top_p is not None:
            body["top_p"] = params.top_p
        if params.response_format:
            body["response_format"] = {"type": params.response_format}
        if params.seed_param and request.seed is not None:
            body[params.seed_param] = request.seed % (2**31)
        body.update(params.extra)
        return body

    def _status_error(self, status: int, attempt: int, attempts: int) -> ProviderError:
        message = f"{self.host}: HTTP {status} (attempt {attempt}/{attempts})"
        if status in AUTH_STATUS:
            return ProviderAuthError(message, status=status)
        return ProviderError(message, status=status, retryable=status in RETRYABLE_STATUS)

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        http = self._settings.http
        ceiling = min(http.backoff_cap_s, http.backoff_base_s * 2 ** (attempt - 1))
        jitter = self._rng.uniform(0, ceiling)
        if retry_after is None:
            return jitter
        return min(max(retry_after, jitter), http.retry_after_cap_s)

    def _parse(self, response: httpx.Response, attempt: int, latency_ms: int) -> ChatResult:
        try:
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            msg = f"{self.host}: malformed chat-completion response"
            raise ProviderError(msg, status=response.status_code) from None
        if not isinstance(text, str):
            msg = f"{self.host}: completion has no text content"
            raise ProviderError(msg, status=response.status_code)
        return ChatResult(
            text=text,
            usage=_usage(data.get("usage"), text),
            finish_reason=choice.get("finish_reason"),
            attempts=attempt,
            latency_ms=latency_ms,
        )


def _usage(raw: object, text: str) -> TokenUsage:
    if isinstance(raw, dict):
        prompt, completion = raw.get("prompt_tokens"), raw.get("completion_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            details = raw.get("completion_tokens_details")
            reasoning = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0
            return TokenUsage(prompt, completion, int(reasoning or 0))
    return TokenUsage(0, math.ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE), estimated=True)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, moment.timestamp() - time.time())


# --------------------------------------------------------------------------- fake


@dataclass
class FakeProvider:
    """Deterministic provider for tests and offline smoke runs (no network).

    Attributes:
        responder: Maps a request to the completion text.
        host: Host label to report.
        api_model_id: Model id to report.
        open_weights_model: Open-weights id to report.
        calls: Every request received, in order.
        failures: Errors to raise on the next calls (consumed first-in, first-out).
    """

    responder: Callable[[ChatRequest], str]
    host: str = "fakehost"
    api_model_id: str = "fake-model"
    open_weights_model: str = "fake/open-weights"
    calls: list[ChatRequest] = field(default_factory=list)
    failures: list[ProviderError] = field(default_factory=list)

    def complete(self, request: ChatRequest) -> ChatResult:
        """Return the responder's text with length-derived token counts.

        Args:
            request: The request.

        Returns:
            The completion.

        Raises:
            ProviderError: When a queued failure is pending.
        """
        self.calls.append(request)
        if self.failures:
            raise self.failures.pop(0)
        text = self.responder(request)
        usage = TokenUsage(math.ceil(request.prompt_chars() / 4), math.ceil(len(text) / 4))
        return ChatResult(text=text, usage=usage, finish_reason="stop", attempts=1, latency_ms=0)


def safe_error_text(error: BaseException, secrets: Sequence[str] = ()) -> str:
    """Render an exception for logs with any known secret removed (defence in depth).

    Args:
        error: The exception.
        secrets: Secret values that must never appear.

    Returns:
        ``<Type>: <message>`` with secrets replaced by ``***``.
    """
    text = f"{type(error).__name__}: {error}"
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text
