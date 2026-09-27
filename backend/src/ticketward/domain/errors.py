"""Domain errors: expected, client-attributable failures.

Every domain error carries a ``public_message`` that is safe to show to API clients.
It must never contain exception text, ticket content, PII or internal identifiers
beyond what the caller already supplied. ``ticketward.api.errors`` maps each class
to an RFC 9457 problem type and HTTP status; unexpected exceptions become a generic
``INTERNAL`` problem instead.
"""

from typing import ClassVar


class DomainError(Exception):
    """Base class for expected business-rule failures.

    Args:
        public_message: Client-safe explanation. Defaults to the class default.
    """

    default_message: ClassVar[str] = "The request could not be completed."

    def __init__(self, public_message: str | None = None) -> None:
        self.public_message = public_message or self.default_message
        super().__init__(self.public_message)


class NotFoundError(DomainError):
    """The requested resource does not exist or is not visible to the caller."""

    default_message = "The requested resource was not found."


class ConflictError(DomainError):
    """The request conflicts with the current state of the resource."""

    default_message = "The request conflicts with the current state of the resource."


class IdempotencyMismatchError(DomainError):
    """An ``Idempotency-Key`` was reused with a different request body (spec §11)."""

    default_message = "The Idempotency-Key was already used with a different request."


class PermissionDeniedError(DomainError):
    """The caller is authenticated but not allowed to perform the action."""

    default_message = "You do not have permission to perform this action."


class RateLimitedError(DomainError):
    """The caller exceeded a rate limit (spec §11).

    Args:
        retry_after_s: Seconds until the caller may retry (sent as ``Retry-After``).
        public_message: Client-safe explanation.
    """

    default_message = "Too many requests. Retry later."

    def __init__(self, retry_after_s: int, public_message: str | None = None) -> None:
        super().__init__(public_message)
        self.retry_after_s = max(1, retry_after_s)


class UpstreamUnavailableError(DomainError):
    """A required dependency (database, model server, provider) is unavailable."""

    default_message = "A required upstream service is temporarily unavailable."


class DemoLockedError(PermissionDeniedError):
    """A privileged action is disabled in the public demo (spec §24.3, code ``DEMO_LOCKED``)."""

    default_message = "This action is disabled in the public demo."


class RefreshSupersededError(ConflictError):
    """A concurrent refresh already rotated the session (spec §11, ``REFRESH_SUPERSEDED``).

    Raised inside the refresh race-grace window; the client retries once and nothing new
    is issued.
    """

    default_message = "The session was refreshed by a concurrent request. Retry once."


class MaintenanceError(UpstreamUnavailableError):
    """The service is in a maintenance window, e.g. the demo reset (spec §24.4).

    Args:
        retry_after_s: Optional seconds until the caller may retry (``Retry-After``).
        public_message: Client-safe explanation.
    """

    default_message = "The service is in a scheduled maintenance window. Retry later."

    def __init__(self, retry_after_s: int | None = None, public_message: str | None = None) -> None:
        super().__init__(public_message)
        self.retry_after_s = None if retry_after_s is None else max(1, retry_after_s)
