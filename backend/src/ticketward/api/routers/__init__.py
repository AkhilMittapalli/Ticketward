"""Versioned API routers (spec §11).

Convention: every router declares its full prefix (``/api/v1/<resource>``) and is
included into the app without an extra prefix. FastAPI (>= 0.13x) composes included
routers lazily and exposes only the router-local path template in ``scope["route"]``;
declaring the full prefix keeps access logs and metrics labelled with the real template.
``tests/unit/test_app_factory.py`` enforces this.
"""

from typing import Final

from fastapi import APIRouter

from ticketward.api.routers import health

ROUTERS: Final[tuple[APIRouter, ...]] = (health.router,)

__all__ = ["ROUTERS"]
