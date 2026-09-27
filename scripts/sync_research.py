"""Publish ``Core files/ERPROT`` research notes to ``docs/research/`` (owner decision D-04).

Run with the backend environment (the logic lives in ``ticketward.tools.publish_research``
so it is linted, type-checked and tested with the backend)::

    make sync-research | make check-research | make scan-research
    python scripts/uv_backend.py run python ../scripts/sync_research.py --check   # without make
"""

import sys
from pathlib import Path

from ticketward.tools.publish_research import main

REPO_ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    sys.exit(main(["--repo-root", str(REPO_ROOT), *sys.argv[1:]]))
