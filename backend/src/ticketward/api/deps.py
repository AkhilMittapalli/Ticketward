"""FastAPI dependencies shared by routers.

Auth marker: every non-public route must declare a dependency marked with
``auth_dependency`` (P4: ``require_roles(...)``, spec §12.2 "Elevation"). The
deny-by-default test in ``tests/security/test_route_auth.py`` walks every route's
dependency tree and fails if a route outside ``PUBLIC_ROUTES`` lacks one.
"""

from collections.abc import Callable, Sequence
from typing import Annotated, Final

from fastapi import Depends, Request

from ticketward.core.config import Settings
from ticketward.domain.errors import UpstreamUnavailableError
from ticketward.services.health import HealthCheck

AUTH_DEPENDENCY_ATTR: Final = "__rf_auth_dependency__"

PUBLIC_ROUTES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("GET", "/api/v1/health/live"),
        ("GET", "/api/v1/health/ready"),
    }
)
"""(method, path template) pairs that intentionally require no authentication."""


def auth_dependency[F: Callable[..., object]](func: F) -> F:
    """Mark ``func`` as an authentication/authorization dependency.

    Args:
        func: Dependency callable (e.g. the result of ``require_roles(...)``).

    Returns:
        The same callable, tagged for the route-auth enumeration test.
    """
    setattr(func, AUTH_DEPENDENCY_ATTR, True)
    return func


def get_app_settings(request: Request) -> Settings:
    """Return the settings the application was created with.

    Args:
        request: Current request.

    Returns:
        Application settings.

    Raises:
        RuntimeError: If the application was not built by ``create_app``.
    """
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        msg = "application settings are not configured; build the app with create_app()"
        raise RuntimeError(msg)
    return settings


def get_readiness_checks(request: Request) -> Sequence[HealthCheck]:
    """Return the readiness checks registered during application startup.

    Args:
        request: Current request.

    Returns:
        The configured checks.

    Raises:
        UpstreamUnavailableError: If startup has not registered any checks (fail closed).
    """
    checks: Sequence[HealthCheck] | None = getattr(request.app.state, "readiness_checks", None)
    if not checks:
        raise UpstreamUnavailableError("The service is not ready.")
    return checks


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ReadinessChecksDep = Annotated[Sequence[HealthCheck], Depends(get_readiness_checks)]
