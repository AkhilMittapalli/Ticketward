"""Export JSON Schemas (``schemas/json/``) and OpenAPI (``docs/openapi.json``).

Run with the backend environment (the logic lives in ``ticketward.tools.export_contracts``
so it is linted, type-checked and tested with the backend)::

    make export-schemas | make check-schemas
    python scripts/uv_backend.py run python ../scripts/export_schemas.py --check   # without make
"""

import sys
from pathlib import Path

from ticketward.tools.export_contracts import main

REPO_ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    sys.exit(main(["--repo-root", str(REPO_ROOT), *sys.argv[1:]]))
