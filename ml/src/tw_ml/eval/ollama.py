"""Minimal Ollama HTTP client for offline evaluation (raw ``/api/generate``; spec v1.1 §9.5).

Only what the bake-off needs, over ``httpx``; the client comes from the single construction site
``tw_ml.datagen.providers.build_http_client`` (no redirects). The transport is injectable, so
tests run against ``httpx.MockTransport`` and never reach a server:

* ``GET /api/version`` and ``GET /api/tags`` for the preflight. The model must already exist
  locally: this client never pulls, creates, copies or deletes models;
* ``GET /api/ps`` records where the loaded model runs (``size_vram`` 0 means CPU only) and, when
  the server reports it, the loaded context length;
* ``POST /api/generate`` (non-streaming) returns the completion text, ``done_reason`` and the
  server timings (``prompt_eval_count``, ``eval_count`` and the ``*_duration`` fields, in
  nanoseconds) plus the client wall time of the attempt that answered.

Retries: a 4xx response is never retried (a bad request stays bad, and an oversized prompt sent
with ``truncate: false`` must fail loudly); connection errors, dropped connections and 5xx
responses are retried ``retries`` times after ``backoff_s`` seconds; read timeouts are not
retried, because a slow model is a measurement. Errors carry the status and Ollama's short error
string, never prompt or completion text.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Final, Self

import httpx

from tw_ml.datagen.providers import build_http_client

ERROR_TEXT_LIMIT: Final = 200


class OllamaError(RuntimeError):
    """A failed Ollama call.

    Attributes:
        kind: ``http_3xx``, ``http_4xx``, ``http_5xx``, ``timeout``, ``connect``, ``transport``
            or ``bad_response``.
        status: HTTP status, when a response arrived.
        attempts: Attempts made.
    """

    def __init__(
        self, kind: str, message: str, *, status: int | None = None, attempts: int = 1
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class LocalModel:
    """A model in ``/api/tags`` (created locally with ``ollama create``)."""

    name: str
    digest: str | None
    quantization_level: str | None
    family: str | None
    parameter_size: str | None


@dataclass(frozen=True, slots=True)
class LoadedModel:
    """A model in ``/api/ps`` (currently loaded)."""

    name: str
    size: int | None
    size_vram: int | None
    context_length: int | None


@dataclass(frozen=True, slots=True)
class GenerateResult:
    """One ``/api/generate`` answer (durations in nanoseconds, as Ollama reports them)."""

    response: str
    done_reason: str | None
    prompt_eval_count: int | None
    prompt_eval_ns: int | None
    eval_count: int | None
    eval_ns: int | None
    total_ns: int | None
    load_ns: int | None
    wall_ms: float
    attempts: int


def canonical_name(name: str) -> str:
    """Ollama's full model name: ``tw-bakeoff-x`` -> ``tw-bakeoff-x:latest``.

    Args:
        name: Model name with or without a tag.

    Returns:
        The name with a tag.
    """
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _json_object(response: httpx.Response, path: str, attempts: int) -> dict[str, Any]:
    try:
        document = response.json()
    except ValueError:
        document = None
    if not isinstance(document, dict):
        msg = f"{path} answered HTTP {response.status_code} without a JSON object"
        raise OllamaError("bad_response", msg, status=response.status_code, attempts=attempts)
    return document


def _short_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return " ".join(str(error).split())[:ERROR_TEXT_LIMIT] if error else ""


class OllamaClient:
    """Synchronous Ollama client with explicit timeouts and a narrow retry policy.

    Args:
        base_url: Server URL, e.g. ``http://127.0.0.1:11434``.
        timeout_s: Read timeout of one request (CPU inference of a 4B model is slow).
        connect_timeout_s: Connect, write and pool timeout.
        retries: Extra attempts after a connection error, a dropped connection or a 5xx.
        backoff_s: Pause before each retry.
        transport: ``httpx`` transport override (tests use ``httpx.MockTransport``).
        sleep: Pause function (tests pass a no-op).
        clock: Monotonic clock in seconds.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float,
        connect_timeout_s: float = 5.0,
        retries: int = 1,
        backoff_s: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        timeout = httpx.Timeout(
            timeout_s, connect=connect_timeout_s, write=connect_timeout_s, pool=connect_timeout_s
        )
        self._client = build_http_client(base_url=base_url, timeout=timeout, transport=transport)
        self._retries = max(0, retries)
        self._backoff_s = backoff_s
        self._sleep = sleep
        self._clock = clock

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection pool."""
        self._client.close()

    def _request(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> tuple[dict[str, Any], float, int]:
        """Send one request with the retry policy; return (JSON body, wall ms, attempts)."""
        attempts = 0
        while True:
            attempts += 1
            started = self._clock()
            try:
                response = self._client.request(method, path, json=body)
            except httpx.ConnectTimeout as exc:
                kind, message, retry = "connect", f"connect timeout ({type(exc).__name__})", True
            except httpx.TimeoutException as exc:
                kind, message, retry = "timeout", f"no answer in time ({type(exc).__name__})", False
            except httpx.ConnectError as exc:
                kind, message, retry = "connect", f"cannot connect ({type(exc).__name__})", True
            except httpx.TransportError as exc:
                kind, message, retry = "transport", f"transport error ({type(exc).__name__})", True
            else:
                wall_ms = (self._clock() - started) * 1000.0
                status = response.status_code
                if response.is_success:
                    return _json_object(response, path, attempts), wall_ms, attempts
                detail = _short_error(response)
                message = f"{path} answered HTTP {status}" + (f": {detail}" if detail else "")
                if not response.is_server_error:  # 4xx, and 3xx (redirects are never followed)
                    kind = "http_4xx" if response.is_client_error else "http_3xx"
                    raise OllamaError(kind, message, status=status, attempts=attempts)
                if attempts > self._retries:
                    raise OllamaError("http_5xx", message, status=status, attempts=attempts)
                self._sleep(self._backoff_s)
                continue
            if not retry or attempts > self._retries:
                raise OllamaError(kind, f"{path}: {message}", attempts=attempts)
            self._sleep(self._backoff_s)

    def version(self) -> str | None:
        """The server version (``GET /api/version``).

        Returns:
            The version string, or ``None`` when the server does not report one.
        """
        document, _, _ = self._request("GET", "/api/version")
        return _text(document.get("version"))

    def local_models(self) -> dict[str, LocalModel]:
        """Models available locally (``GET /api/tags``), keyed by canonical name.

        Returns:
            Name to model.
        """
        document, _, _ = self._request("GET", "/api/tags")
        found: dict[str, LocalModel] = {}
        for entry in document.get("models") or ():
            if not isinstance(entry, dict):
                continue
            name = _text(entry.get("name")) or _text(entry.get("model"))
            if name is None:
                continue
            raw_details = entry.get("details")
            details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
            found[canonical_name(name)] = LocalModel(
                name=canonical_name(name),
                digest=_text(entry.get("digest")),
                quantization_level=_text(details.get("quantization_level")),
                family=_text(details.get("family")),
                parameter_size=_text(details.get("parameter_size")),
            )
        return found

    def loaded_models(self) -> dict[str, LoadedModel]:
        """Models currently loaded (``GET /api/ps``), keyed by canonical name.

        Returns:
            Name to loaded model.
        """
        document, _, _ = self._request("GET", "/api/ps")
        found: dict[str, LoadedModel] = {}
        for entry in document.get("models") or ():
            name = _text(entry.get("name")) if isinstance(entry, dict) else None
            if name is None or not isinstance(entry, dict):
                continue
            found[canonical_name(name)] = LoadedModel(
                name=canonical_name(name),
                size=_int(entry.get("size")),
                size_vram=_int(entry.get("size_vram")),
                context_length=_int(entry.get("context_length")),
            )
        return found

    def generate(self, payload: Mapping[str, Any]) -> GenerateResult:
        """``POST /api/generate`` without streaming.

        Args:
            payload: Request body (``model``, ``prompt``, ``raw``, ``format``, ``options``...).

        Returns:
            The completion and its timings.

        Raises:
            OllamaError: On an HTTP error, timeout, connection failure or malformed answer.
        """
        document, wall_ms, attempts = self._request("POST", "/api/generate", payload)
        response = document.get("response")
        if not isinstance(response, str):
            msg = "/api/generate answered without a response text"
            raise OllamaError("bad_response", msg, attempts=attempts)
        return GenerateResult(
            response=response,
            done_reason=_text(document.get("done_reason")),
            prompt_eval_count=_int(document.get("prompt_eval_count")),
            prompt_eval_ns=_int(document.get("prompt_eval_duration")),
            eval_count=_int(document.get("eval_count")),
            eval_ns=_int(document.get("eval_duration")),
            total_ns=_int(document.get("total_duration")),
            load_ns=_int(document.get("load_duration")),
            wall_ms=wall_ms,
            attempts=attempts,
        )
