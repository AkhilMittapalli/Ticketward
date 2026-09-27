import json
import logging
from typing import Any

import pytest

from ticketward.core.logging import (
    REDACTED,
    configure_logging,
    get_logger,
    redact_sensitive,
    scrub_text,
)


def redact(**event: Any) -> dict[str, Any]:
    return dict(redact_sensitive(None, "info", dict(event)))


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "db_password",
        "Authorization",
        "cookie",
        "Set-Cookie",
        "token",
        "refresh_token",
        "api_key",
        "X-Api-Key",
        "client_secret",
        "database_dsn",
        "message",
        "ticket_message",
        "body",
        "raw_body",
        "email",
        "customer_email",
        "subject",
        "prompt",
    ],
)
def test_sensitive_keys_are_redacted(key: str) -> None:
    assert redact(**{key: "value"})[key] == REDACTED


@pytest.mark.parametrize("key", ["message_length", "ticket_id", "status", "route", "email_domain"])
def test_non_sensitive_keys_are_kept(key: str) -> None:
    assert redact(**{key: "value"})[key] == "value"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("input_tokens", 412),
        ("output_tokens", 51),
        ("prompt_tokens", 380),
        ("completion_tokens", 120),
        ("total_tokens", 500),
        ("max_tokens", 600),
        ("token_count", 350),
        ("rerank_token_count", 12),
        ("cached_input_tokens", 64),
        ("draft_output_tokens", 0.0),
    ],
)
def test_numeric_token_counts_survive(key: str, value: float) -> None:
    assert redact(**{key: value})[key] == value


def test_allow_list_is_narrow_other_token_keys_fail_safe() -> None:
    # Only exact count names and *_tokens / *_token_count suffixes are allowed through.
    assert redact(tokens_per_second=18.5)["tokens_per_second"] == REDACTED


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("access_token", "eyJ-not-really"),
        ("refresh_token", "opaque-refresh"),
        ("x_api_key", "tm_live_abcdefgh"),
        ("authorization", "Bearer abc"),
        ("db_password", "hunter2"),
        ("access_token", 12345),  # numeric but not a *_tokens count key
        ("input_tokens", "sk-ant-api03-leaked"),  # string under a count key
        ("max_tokens", "600"),
        ("input_tokens", True),  # booleans are not counts
    ],
)
def test_credentials_stay_redacted_despite_the_token_count_allow_list(
    key: str, value: object
) -> None:
    assert redact(**{key: value})[key] == REDACTED


def test_nested_token_counts_survive() -> None:
    usage = {"input_tokens": 412, "output_tokens": 51, "api_key": "k"}
    assert redact(usage=usage)["usage"] == {
        "input_tokens": 412,
        "output_tokens": 51,
        "api_key": REDACTED,
    }


def test_event_is_scrubbed_but_never_key_redacted() -> None:
    result = redact(event="login failed for alice@example.com")
    assert result["event"] == "login failed for [EMAIL]"


def test_nested_structures_are_redacted_and_scrubbed() -> None:
    result = redact(
        context={"headers": {"authorization": "Bearer abc", "accept": "json"}},
        items=[{"password": "x"}, "call +1 bob@example.org", 42],
        blob=b"raw ticket bytes",
    )
    assert result["context"] == {"headers": {"authorization": REDACTED, "accept": "json"}}
    assert result["items"] == [{"password": REDACTED}, "call +1 [EMAIL]", 42]
    assert result["blob"] == "[BYTES len=16]"


def test_deeply_nested_values_are_truncated() -> None:
    value: dict[str, Any] = {"leaf": "x"}
    for _ in range(10):
        value = {"level": value}
    serialized = json.dumps(redact(nested=value))
    assert "[TRUNCATED]" in serialized
    assert '"leaf"' not in serialized


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail alice.smith+tag@example.co.uk now", "mail [EMAIL] now"),
        ("card 4111111111111111 declined", "card [CARD] declined"),
        ("card 4111 1111 1111 1111 declined", "card [CARD] declined"),
        ("card 4111-1111-1111-1111 declined", "card [CARD] declined"),
        ("Authorization: Bearer eyJhbGciOi.abc.def", "Authorization: Bearer [REDACTED]"),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl", "jwt [JWT]"),
        ("key sk-ant-api03-abcdefghijkl", "key [API_KEY]"),
        ("key tm_live_4f9a8b7c6d5e", "key [API_KEY]"),
        (
            "postgresql+asyncpg://rf:s3cr3t@db:5432/rf",
            f"postgresql+asyncpg://rf:{REDACTED}@db:5432/rf",
        ),
        (
            "[type=string_too_long, input_value='my ssn is ...', input_type=str]",
            f"[type=string_too_long, input_value={REDACTED}, input_type=str]",
        ),
        ("order 12345 shipped", "order 12345 shipped"),
        # v1.1 §12.10: phones and IBANs are scrubbed too
        ("call +1 415 555 0100 now", "call [PHONE] now"),
        ("tel +44 20 7946 0958.", "tel [PHONE]."),
        ("tel +49-30-1234567", "tel [PHONE]"),
        ("office (415) 555-0100", "office [PHONE]"),
        ("mobile 415-555-0100 or 415.555.0101", "mobile [PHONE] or [PHONE]"),
        ("iban DE89 3704 0044 0532 0130 00 ok", "iban [IBAN] ok"),
        ("iban GB82WEST12345698765432", "iban [IBAN]"),
    ],
)
def test_scrub_text(text: str, expected: str) -> None:
    assert scrub_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "reset at 2026-09-27T03:00:00Z",
        "run 2026-09-27 12:30",
        "client 192.168.100.200 connected",
        "version 1.20.3 and build 20260927",
        "retry +1 later",
        "+12 retries",
        "latency 1234 ms, 56 tokens",
        "HTTP 429 after 3 attempts",
    ],
)
def test_scrubbers_leave_ordinary_numbers_alone(text: str) -> None:
    assert scrub_text(text) == text


@pytest.mark.parametrize(
    "identifier", ["3f2b8c1e-1234-4567-8901-123456789012", "01J8ZB4Q2X7N5M3K1H9G6F4D2C"]
)
def test_identifiers_are_not_scrubbed(identifier: str) -> None:
    assert scrub_text(identifier) == identifier


def test_configure_logging_emits_redacted_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_logs=True)
    log = get_logger("ticketward.test")
    log.info("ticket.received", ticket_id="t-1", message="my card is 4111111111111111")
    try:
        raise ValueError("lookup failed for alice@example.com")
    except ValueError:
        log.exception("ticket.failed")

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    received, failed = lines[-2], lines[-1]
    assert received["event"] == "ticket.received"
    assert received["level"] == "info"
    assert received["message"] == REDACTED
    assert received["ticket_id"] == "t-1"
    assert received["timestamp"].endswith("Z")
    assert "alice@example.com" not in failed["exception"]
    assert "[EMAIL]" in failed["exception"]


def test_stdlib_loggers_share_the_redacting_pipeline(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_logs=True)
    logging.getLogger("uvicorn.error").warning("client bob@example.org disconnected")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "client [EMAIL] disconnected"
    assert line["logger"] == "uvicorn.error"


def test_console_renderer_for_local_development(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="DEBUG", json_logs=False)
    get_logger("ticketward.test").debug("dev.event", password="hunter2")
    out = capsys.readouterr().out
    assert "dev.event" in out
    assert "hunter2" not in out


def test_access_log_is_disabled_for_uvicorn() -> None:
    configure_logging()
    assert logging.getLogger("uvicorn.access").disabled is True
    assert logging.getLogger("uvicorn.error").propagate is True
