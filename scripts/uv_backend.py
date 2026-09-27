"""Run ``uv`` for the backend project with the virtualenv kept outside the repository.

Developer tooling only: it shells out to the ``uv`` CLI with the caller's arguments.

Used by pre-commit hooks so a missing ``UV_PROJECT_ENVIRONMENT`` never creates
``backend/.venv`` inside the OneDrive-synced checkout (risk R-13)::

    python scripts/uv_backend.py run --frozen mypy src
    python scripts/uv_backend.py lock --check
"""

import os
import subprocess  # nosec B404
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
DEFAULT_VENV = Path.home() / ".venvs" / "ticketward-backend"


def main(argv: list[str]) -> int:
    """Run ``uv <argv>`` in ``backend/`` and return its exit code."""
    env = dict(os.environ)
    env.setdefault("UV_PROJECT_ENVIRONMENT", str(DEFAULT_VENV))
    # Intentionally runs the developer's `uv` from PATH with hook-supplied arguments.
    completed = subprocess.run(  # noqa: S603  # nosec B603 B607
        ["uv", *argv],  # noqa: S607
        cwd=BACKEND_DIR,
        env=env,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
