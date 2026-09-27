"""Ticketward backend package.

An evidence-first, human-in-the-loop customer-support resolution copilot. See
``TICKETWARD_SPEC.md`` (the source of truth) for scope and contracts.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ticketward")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
