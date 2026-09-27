"""Structured JSON logging with redaction (spec §12.10, §15).

* structlog renders one JSON object per line to stdout; stdlib loggers (uvicorn,
  SQLAlchemy, Alembic) are routed through the same processor chain.
* ``redact_sensitive`` runs after exception formatting, so tracebacks are scrubbed too.
  It (1) replaces values of sensitive keys (credentials and ticket-content keys such as
  ``message``/``body``/``email``) and (2) scrubs every other string with regexes for
  e-mail addresses, phone numbers, IBANs, card-like numbers, bearer tokens, JWTs, API
  keys and URL credentials (spec v1.1 §12.10). Numeric token counts are kept (A-25(i)).
* Ticket text must never be logged: log ids and lengths. Redaction is a safety net,
  not a license to log content.
"""

import logging
import re
import sys
from collections.abc import Callable, Mapping
from typing import Final

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

REDACTED: Final = "[REDACTED]"
_MAX_DEPTH: Final = 6

_CREDENTIAL_KEY_PARTS: Final = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "dsn",
)
"""Key substrings that always mark a credential (``db_password``, ``x_api_key`` ...)."""

_CONTENT_KEYS: Final = (
    "message",
    "body",
    "email",
    "subject",
    "content",
    "text",
    "prompt",
    "completion",
)
"""Content keys, matched exactly or as a ``_suffix`` (``customer_email``, ``raw_body``)."""

_TOKEN_COUNT_KEYS: Final = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "max_tokens",
        "token_count",
    }
)
_TOKEN_COUNT_SUFFIXES: Final = ("_tokens", "_token_count")
"""LLM token *counts* are cost/latency telemetry (spec §15, M-09/M-10), not credentials.

They bypass the ``token`` credential rule only when the value is numeric, so a string
logged under e.g. ``input_tokens`` is still redacted.
"""

_NEVER_SCRUB_KEYS: Final = frozenset({"timestamp", "level", "logger", "request_id"})

_ID_RE: Final = re.compile(
    r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9A-HJKMNP-TV-Z]{26})$"
)
"""Canonical UUIDs and ULIDs are identifiers, not PII; skipping them avoids false positives."""

_PHONE_DIGITS_MIN: Final = 8
_PHONE_DIGITS_MAX: Final = 15  # E.164 maximum


def _international_phone(match: re.Match[str]) -> str:
    digits = sum(character.isdigit() for character in match.group(0))
    return "[PHONE]" if _PHONE_DIGITS_MIN <= digits <= _PHONE_DIGITS_MAX else match.group(0)


type _Replacement = str | Callable[[re.Match[str]], str]

_SCRUBBERS: Final[tuple[tuple[re.Pattern[str], _Replacement], ...]] = (
    # scheme://user:password@host -> keep user, drop password
    (re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^:/?#\s@]*:)[^@/?#\s]+@"), rf"\1{REDACTED}@"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]+"), f"Bearer {REDACTED}"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}"), "[JWT]"),
    (re.compile(r"\b(?:sk-ant-[A-Za-z0-9_\-]{8,}|tm_(?:live|test)_[A-Za-z0-9]{8,})"), "[API_KEY]"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # IBANs before cards: their digit groups would otherwise look card-like
    (re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b"), "[IBAN]"),
    # 13-19 digit card-like numbers, contiguous or in groups of four
    (re.compile(r"(?<!\d)(?:\d{13,19}|\d{4}(?:[ \-]\d{4}){2,3}(?:[ \-]\d{1,3})?)(?!\d)"), "[CARD]"),
    # phones: international "+" form (8-15 digits) and NANP (415) 555-0100 / 415-555-0100
    (re.compile(r"(?<![\w+])\+\d[\d .\-()]{5,18}\d(?!\w)"), _international_phone),
    (re.compile(r"(?<!\w)(?:\(\d{3}\) ?|\d{3}[-. ])\d{3}[-. ]\d{4}(?!\w)"), "[PHONE]"),
    # pydantic ValidationError reprs echo the offending input
    (
        re.compile(r"input_value=(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|[^,\]\s]+)"),
        f"input_value={REDACTED}",
    ),
)


def _is_token_count(normalized_key: str, value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return normalized_key in _TOKEN_COUNT_KEYS or normalized_key.endswith(_TOKEN_COUNT_SUFFIXES)


def _is_sensitive_key(key: str, value: object) -> bool:
    normalized = key.lower().replace("-", "_")
    if _is_token_count(normalized, value):
        return False
    if any(part in normalized for part in _CREDENTIAL_KEY_PARTS):
        return True
    return any(normalized == name or normalized.endswith("_" + name) for name in _CONTENT_KEYS)


def scrub_text(value: str) -> str:
    """Remove PII- and secret-looking substrings from free text.

    Args:
        value: Arbitrary text (log message, exception text, traceback).

    Returns:
        The text with matches replaced by typed placeholders such as ``[EMAIL]``.
    """
    if _ID_RE.fullmatch(value):
        return value
    for pattern, replacement in _SCRUBBERS:
        value = pattern.sub(replacement, value)
    return value


def _redact_value(value: object, depth: int) -> object:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"[BYTES len={len(value)}]"
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and _is_sensitive_key(key, item)
                else _redact_value(item, depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [_redact_value(item, depth + 1) for item in value]
    return value


def redact_sensitive(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Redact sensitive keys and scrub string values (a structlog processor).

    Args:
        _logger: Wrapped logger (unused).
        _method_name: Log method name (unused).
        event_dict: Event being logged.

    Returns:
        The redacted event dictionary.
    """
    for key, value in list(event_dict.items()):
        if key in _NEVER_SCRUB_KEYS:
            continue
        if key != "event" and _is_sensitive_key(key, value):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact_value(value, depth=0)
    return event_dict


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive,
    ]


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog and stdlib logging for the process. Idempotent.

    Loggers are not cached on first use, so reconfiguration (and
    ``structlog.testing.capture_logs``) always takes effect; the per-call cost is a
    dictionary lookup, negligible at this service's log volume.

    Args:
        level: Root log level name.
        json_logs: Render JSON (production) or a console format (local dev).
    """
    shared = _shared_processors()
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy", "alembic"):
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers = []
        stdlib_logger.propagate = True
    # The request-id middleware emits one structured access line per request.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to ``name``.

    Args:
        name: Logger name, conventionally ``__name__``.

    Returns:
        A lazily-bound structlog logger.
    """
    return structlog.stdlib.get_logger(name)
