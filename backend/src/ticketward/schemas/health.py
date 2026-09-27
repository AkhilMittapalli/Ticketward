"""Health endpoint contracts (spec §11, §15)."""

from typing import Literal

from ticketward.schemas.common import ContractModel


class LiveResponse(ContractModel):
    """Liveness: the process is up and serving requests."""

    status: Literal["ok"] = "ok"


class ReadyResponse(ContractModel):
    """Readiness: every dependency check passed.

    Failures are reported as a 503 problem without component detail; the failing
    components are logged server-side with the request id.
    """

    status: Literal["ok"] = "ok"
    checks: dict[str, Literal["ok"]]
