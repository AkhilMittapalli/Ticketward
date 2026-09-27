"""Container ``HEALTHCHECK`` probe: ``python -m ticketward.healthcheck``.

Standard library only (the runtime image ships no curl/wget). Exits 0 when the
liveness endpoint on the loopback interface answers 200, otherwise 1.
"""

import sys
import urllib.request
from typing import Final

LIVE_URL: Final = "http://127.0.0.1:8000/api/v1/health/live"
_HTTP_OK: Final = 200


def probe(url: str = LIVE_URL, timeout_s: float = 3.0) -> bool:
    """Return whether ``url`` answers HTTP 200 within ``timeout_s``.

    Args:
        url: Loopback liveness URL.
        timeout_s: Socket timeout in seconds.

    Returns:
        ``True`` on HTTP 200, ``False`` on any error or other status.

    Raises:
        ValueError: If ``url`` is not a plain-HTTP loopback URL.
    """
    if not url.startswith("http://127.0.0.1:"):
        msg = "the healthcheck only probes http://127.0.0.1"
        raise ValueError(msg)
    try:
        # Scheme and host are validated above (plain HTTP to 127.0.0.1 only).
        with urllib.request.urlopen(url, timeout=timeout_s) as response:  # noqa: S310  # nosec B310
            return bool(response.status == _HTTP_OK)
    except OSError:
        return False


def main() -> int:
    """Run the probe and return a process exit code."""
    return 0 if probe() else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
