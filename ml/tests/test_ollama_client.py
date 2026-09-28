"""The minimal Ollama client: parsing, timeouts and the retry policy (httpx.MockTransport)."""

import json
from collections.abc import Callable, Iterator

import httpx
import pytest

from tw_ml.eval.ollama import OllamaClient, OllamaError, canonical_name

Handler = Callable[[httpx.Request], httpx.Response]
GENERATED = {
    "model": "tw-bakeoff-x",
    "response": '{"intent": "bug_report"}',
    "done": True,
    "done_reason": "stop",
    "total_duration": 2_500_000_000,
    "load_duration": 1_000_000,
    "prompt_eval_count": 900,
    "prompt_eval_duration": 1_500_000_000,
    "eval_count": 120,
    "eval_duration": 900_000_000,
}


class Clock:
    """A clock that advances 0.25 s per reading."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.25
        return self.now


def _client(handler: Handler, sleeps: list[float], *, retries: int = 1) -> OllamaClient:
    return OllamaClient(
        "http://ollama.test",
        timeout_s=30.0,
        retries=retries,
        backoff_s=2.0,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        clock=Clock(),
    )


def _sequence(*steps: httpx.Response | Exception) -> tuple[Handler, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue: Iterator[httpx.Response | Exception] = iter(steps)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        step = next(queue)
        if isinstance(step, Exception):
            raise step
        return step

    return handler, seen


def test_generate_parses_timings_and_measures_wall_time() -> None:
    handler, seen = _sequence(httpx.Response(200, json=GENERATED))
    sleeps: list[float] = []
    with _client(handler, sleeps) as client:
        result = client.generate({"model": "tw-bakeoff-x", "prompt": "p", "raw": True})
    assert json.loads(seen[0].content) == {"model": "tw-bakeoff-x", "prompt": "p", "raw": True}
    assert seen[0].url.path == "/api/generate"
    assert result.response == '{"intent": "bug_report"}'
    assert (result.done_reason, result.prompt_eval_count, result.eval_count) == ("stop", 900, 120)
    assert (result.total_ns, result.load_ns, result.eval_ns) == (
        2_500_000_000,
        1_000_000,
        900_000_000,
    )
    assert result.wall_ms == pytest.approx(250.0)
    assert (result.attempts, sleeps) == (1, [])


def test_client_errors_are_never_retried() -> None:
    handler, seen = _sequence(httpx.Response(400, json={"error": "prompt too long\nfor context"}))
    with _client(handler, []) as client, pytest.raises(OllamaError) as excinfo:
        client.generate({"model": "m"})
    assert (excinfo.value.kind, excinfo.value.status, excinfo.value.attempts) == (
        "http_4xx",
        400,
        1,
    )
    assert "prompt too long for context" in str(excinfo.value)
    assert len(seen) == 1


def test_server_errors_and_dropped_connections_are_retried() -> None:
    handler, seen = _sequence(httpx.Response(503, text="busy"), httpx.Response(200, json=GENERATED))
    sleeps: list[float] = []
    with _client(handler, sleeps) as client:
        assert client.generate({"model": "m"}).attempts == 2
    assert (len(seen), sleeps) == (2, [2.0])
    handler, seen = _sequence(
        httpx.RemoteProtocolError("dropped"), httpx.Response(200, json=GENERATED)
    )
    with _client(handler, []) as client:
        assert client.generate({"model": "m"}).attempts == 2


@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        (httpx.ConnectError("refused"), "connect"),
        (httpx.ConnectTimeout("slow connect"), "connect"),
        (httpx.RemoteProtocolError("dropped"), "transport"),
    ],
)
def test_retries_are_bounded(failure: Exception, kind: str) -> None:
    handler, seen = _sequence(failure, failure, failure)
    with _client(handler, [], retries=1) as client, pytest.raises(OllamaError) as excinfo:
        client.version()
    assert (excinfo.value.kind, excinfo.value.attempts, len(seen)) == (kind, 2, 2)


def test_exhausted_server_errors_keep_their_status() -> None:
    handler, _ = _sequence(httpx.Response(500, json={"error": "boom"}), httpx.Response(502))
    with _client(handler, []) as client, pytest.raises(OllamaError) as excinfo:
        client.generate({"model": "m"})
    assert (excinfo.value.kind, excinfo.value.status, excinfo.value.attempts) == (
        "http_5xx",
        502,
        2,
    )


def test_read_timeouts_are_measurements_not_retried() -> None:
    handler, seen = _sequence(httpx.ReadTimeout("slow model"))
    with _client(handler, []) as client, pytest.raises(OllamaError) as excinfo:
        client.generate({"model": "m"})
    assert (excinfo.value.kind, len(seen)) == ("timeout", 1)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["a", "list"]),
        httpx.Response(200, json={"done": True}),
    ],
)
def test_malformed_answers_are_bad_responses(response: httpx.Response) -> None:
    handler, _ = _sequence(response)
    with _client(handler, []) as client, pytest.raises(OllamaError) as excinfo:
        client.generate({"model": "m"})
    assert excinfo.value.kind == "bad_response"


def test_redirects_are_never_followed() -> None:
    redirect = httpx.Response(307, headers={"Location": "http://elsewhere.test/api/generate"})
    handler, seen = _sequence(redirect, httpx.Response(200, json=GENERATED))
    with _client(handler, []) as client, pytest.raises(OllamaError) as excinfo:
        client.generate({"model": "m"})
    assert (excinfo.value.kind, excinfo.value.status, len(seen)) == ("http_3xx", 307, 1)


def test_error_bodies_without_json_give_a_bare_status() -> None:
    handler, _ = _sequence(httpx.Response(404, text="<html>nope</html>"))
    with _client(handler, []) as client, pytest.raises(OllamaError) as excinfo:
        client.version()
    assert str(excinfo.value) == "/api/version answered HTTP 404"


def test_version_tags_and_ps_are_parsed() -> None:
    tags = {
        "models": [
            {
                "name": "tw-bakeoff-qwen35-2b:latest",
                "digest": "ab" * 32,
                "details": {
                    "quantization_level": "Q4_K_M",
                    "family": "qwen35",
                    "parameter_size": "2B",
                },
            },
            {"model": "other"},
            "junk",
            {"digest": "no-name"},
        ]
    }
    ps = {
        "models": [
            {"name": "tw-bakeoff-qwen35-2b", "size": 10, "size_vram": 0, "context_length": 8192},
            7,
        ]
    }
    handler, _ = _sequence(
        httpx.Response(200, json={"version": "0.34.4"}),
        httpx.Response(200, json=tags),
        httpx.Response(200, json=ps),
        httpx.Response(200, json={}),
    )
    with _client(handler, []) as client:
        assert client.version() == "0.34.4"
        models = client.local_models()
        loaded = client.loaded_models()
        assert client.version() is None
    assert set(models) == {"tw-bakeoff-qwen35-2b:latest", "other:latest"}
    local = models["tw-bakeoff-qwen35-2b:latest"]
    assert (local.digest, local.quantization_level, local.parameter_size) == (
        "ab" * 32,
        "Q4_K_M",
        "2B",
    )
    assert models["other:latest"].quantization_level is None
    running = loaded["tw-bakeoff-qwen35-2b:latest"]
    assert (running.size_vram, running.context_length) == (0, 8192)


@pytest.mark.parametrize(
    ("name", "full"),
    [
        ("tw-bakeoff-x", "tw-bakeoff-x:latest"),
        ("tw-bakeoff-x:q4", "tw-bakeoff-x:q4"),
        ("registry.test:5000/ns/model", "registry.test:5000/ns/model:latest"),
    ],
)
def test_canonical_names(name: str, full: str) -> None:
    assert canonical_name(name) == full
