"""Export JSON Schemas (``schemas/json/``) and OpenAPI (``docs/openapi.json``).

``schemas/json/<stem>.schema.json`` are the contract schemas; ``<stem>.decoding.json`` are the
grammar-safe decoding schemas derived from them (``ticketward.ml.decoding_schema``, spec §6),
sent as the Ollama ``format``. ``--check`` covers every file.

Usage (from the repository root)::

    make export-schemas   # write files
    make check-schemas    # CI: fail if stale

Without make, ``scripts/uv_backend.py`` keeps the virtualenv outside the OneDrive checkout::

    python scripts/uv_backend.py run python ../scripts/export_schemas.py --check
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ticketward.core.config import Environment, Settings
from ticketward.ml.decoding_schema import build_decoding_schemas
from ticketward.schemas.export import build_json_schemas, render_json


def build_openapi() -> dict[str, Any]:
    """Build the OpenAPI document from a hermetic test-mode application.

    Returns:
        The OpenAPI 3.1 document.
    """
    from ticketward.main import create_app  # noqa: PLC0415 - keep CLI import-light

    app = create_app(Settings(env=Environment.test, docs_enabled=True, log_level="WARNING"))
    return app.openapi()


def contract_files(repo_root: Path) -> dict[Path, str]:
    """Render every exported contract file.

    Args:
        repo_root: Repository root directory.

    Returns:
        Mapping of absolute output path to file content.
    """
    schema_dir = repo_root / "schemas" / "json"
    files = {
        schema_dir / f"{name}.schema.json": render_json(schema)
        for name, schema in build_json_schemas().items()
    }
    files.update(
        (schema_dir / f"{name}.decoding.json", render_json(schema))
        for name, schema in build_decoding_schemas().items()
    )
    files[repo_root / "docs" / "openapi.json"] = render_json(build_openapi())
    return files


def sync_contract_files(repo_root: Path, *, check: bool) -> list[Path]:
    """Write (or, with ``check``, only compare) the contract files.

    Args:
        repo_root: Repository root directory.
        check: Do not write; only report files whose content differs.

    Returns:
        Paths whose on-disk content differed from the generated content.
    """
    stale: list[Path] = []
    for path, content in contract_files(repo_root).items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        stale.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    return stale


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 on success, 1 when ``--check`` finds stale files.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--check", action="store_true", help="fail if files are out of date")
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root.resolve()
    stale = sync_contract_files(repo_root, check=args.check)
    relative = [path.relative_to(repo_root).as_posix() for path in stale]
    if args.check and stale:
        sys.stderr.write(
            "Contract files are out of date; run scripts/export_schemas.py:\n  "
            + "\n  ".join(relative)
            + "\n"
        )
        return 1
    sys.stdout.write(
        ("Updated:\n  " + "\n  ".join(relative) + "\n") if stale else "Contracts up to date.\n"
    )
    return 0
