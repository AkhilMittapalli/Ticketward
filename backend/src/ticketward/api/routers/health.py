"""Health endpoints (spec §11, §15). Both are public (see ``PUBLIC_ROUTES``).

* ``GET /api/v1/health/live``: process is up; touches no dependencies.
* ``GET /api/v1/health/ready``: database and Redis reachable; 503 problem otherwise.
  Only exposed on the internal network once the reverse proxy lands (P9).
"""

from fastapi import APIRouter

from ticketward.api import API_V1_PREFIX
from ticketward.api.deps import ReadinessChecksDep, SettingsDep
from ticketward.domain.errors import UpstreamUnavailableError
from ticketward.schemas.health import LiveResponse, ReadyResponse
from ticketward.schemas.problem import ProblemDetail
from ticketward.services.health import run_checks

router = APIRouter(prefix=f"{API_V1_PREFIX}/health", tags=["health"])


@router.get("/live", summary="Liveness probe")
async def live() -> LiveResponse:
    """Report that the process is serving requests.

    Returns:
        ``{"status": "ok"}``.
    """
    return LiveResponse()


@router.get(
    "/ready",
    summary="Readiness probe",
    responses={
        503: {"model": ProblemDetail, "description": "One or more dependencies are unavailable."}
    },
)
async def ready(checks: ReadinessChecksDep, settings: SettingsDep) -> ReadyResponse:
    """Check every backing service required to serve traffic.

    Args:
        checks: Registered dependency checks.
        settings: Application settings (per-check timeout).

    Returns:
        ``{"status": "ok", "checks": {...}}`` when all checks pass.

    Raises:
        UpstreamUnavailableError: If any check fails or times out (503).
    """
    outcomes = await run_checks(checks, timeout_s=settings.ready_check_timeout_s)
    if not all(outcome.ok for outcome in outcomes):
        raise UpstreamUnavailableError("One or more dependencies are unavailable.")
    return ReadyResponse(checks={outcome.name: "ok" for outcome in outcomes})
