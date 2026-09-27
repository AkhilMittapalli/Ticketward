"""RFC 9457 problem details contract (spec §11 "Error envelope", ADR-0025)."""

from enum import StrEnum, unique
from typing import Final

from pydantic import Field

from ticketward.schemas.common import ContractModel

PROBLEM_MEDIA_TYPE: Final = "application/problem+json"
PROBLEM_TYPE_BASE: Final = "/problems/"
"""Relative problem-type URI prefix (RFC 9457 allows relative references; A-25(j))."""


@unique
class ErrorCode(StrEnum):
    """Stable machine-readable error codes (spec v1.1 §11)."""

    BAD_REQUEST = "BAD_REQUEST"  # 400
    VALIDATION_ERROR = "VALIDATION_ERROR"  # 422
    UNAUTHENTICATED = "UNAUTHENTICATED"  # 401
    FORBIDDEN = "FORBIDDEN"  # 403
    CSRF_FAILED = "CSRF_FAILED"  # 403
    DEMO_LOCKED = "DEMO_LOCKED"  # 403, privileged action in demo mode (§24.3)
    NOT_FOUND = "NOT_FOUND"  # 404
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"  # 405
    CONFLICT = "CONFLICT"  # 409
    REFRESH_SUPERSEDED = "REFRESH_SUPERSEDED"  # 409, refresh race grace; client retries once
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"  # 422
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"  # 413
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"  # 415
    RATE_LIMITED = "RATE_LIMITED"  # 429 (+ Retry-After)
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"  # 503
    MAINTENANCE = "MAINTENANCE"  # 503, demo reset window (§24.4)
    INTERNAL = "INTERNAL"  # 500, generic detail only


def problem_type_uri(code: ErrorCode) -> str:
    """Return the relative problem ``type`` URI for ``code``.

    Args:
        code: Error code.

    Returns:
        A relative URI such as ``/problems/validation-error``.
    """
    return PROBLEM_TYPE_BASE + code.value.lower().replace("_", "-")


class FieldError(ContractModel):
    """One request-validation failure. The offending input is never echoed back."""

    loc: list[str | int] = Field(description="Path to the invalid value, e.g. ['body', 'subject'].")
    msg: str = Field(max_length=256, description="Human-readable constraint violation.")
    type: str = Field(max_length=64, description="Pydantic error type, e.g. 'string_too_long'.")


class ProblemDetail(ContractModel):
    """``application/problem+json`` body returned for every error response."""

    type: str = Field(description="Problem type URI.")
    title: str = Field(description="Short, stable summary of the problem type.")
    status: int = Field(ge=100, le=599, description="HTTP status code.")
    detail: str = Field(description="Client-safe explanation. Never contains exception text.")
    instance: str | None = Field(default=None, description="Request path (no query string).")
    code: ErrorCode = Field(description="Stable machine-readable error code.")
    request_id: str | None = Field(default=None, description="Correlates with server logs.")
    errors: list[FieldError] | None = Field(
        default=None, description="Field errors (validation failures only)."
    )
