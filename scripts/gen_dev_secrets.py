"""Create the local Docker secret files in ``secrets/`` (never committed).

Standard library only; runs with any Python 3.10+::

    python scripts/gen_dev_secrets.py           # create missing files
    python scripts/gen_dev_secrets.py --force   # rotate all (then `docker compose down -v`)

Values are 64 hex characters from ``secrets.token_hex``: strong, and never matching the
placeholder markers the prod settings validator rejects.
"""

import argparse
import secrets
import sys
from pathlib import Path

SECRET_NAMES = ("tw_db_password", "tw_redis_password")
SECRETS_DIR = Path(__file__).resolve().parents[1] / "secrets"


def main(argv: list[str]) -> int:
    """Create (or rotate) the secret files and return a process exit code."""
    parser = argparse.ArgumentParser(description="Generate local Docker secret files.")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args(argv)

    SECRETS_DIR.mkdir(exist_ok=True)
    for name in SECRET_NAMES:
        path = SECRETS_DIR / name
        if path.exists() and not args.force:
            print(f"kept     secrets/{name} (use --force to rotate)")
            continue
        path.write_text(secrets.token_hex(32) + "\n", encoding="utf-8", newline="\n")
        # Containers read these as non-root UIDs; Compose cannot chown file secrets.
        path.chmod(0o644)
        print(f"created  secrets/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
