"""HTTP layer: routers, middleware, dependencies and RFC 9457 error handling."""

from typing import Final

API_V1_PREFIX: Final = "/api/v1"
"""URI major version prefix (spec §11). Routers declare it in their own ``prefix``."""
