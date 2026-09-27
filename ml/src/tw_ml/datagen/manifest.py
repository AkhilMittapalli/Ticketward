"""Content-hash manifests, freeze and verify (spec v1.1 §9.3; P1.28).

``data/manifests/<split>.json`` records, for one split version, the SHA-256 of every file, the
record count and a content digest (sorted ``record_id:content_sha256`` lines), plus named
subsets with their seeds (``val_dev`` 225 of val; ``hard_dev`` / ``hard_final`` of test_hard).

At the P1 exit the protected splits are frozen. After that a frozen manifest is immutable:
``verify`` fails when any file or record changed, and ``freeze`` refuses different content
unless ``bump`` is passed, which archives the old manifest (``<split>.<version>.json``) and
writes the next version (``v2``...), because any test change means re-running E1-E6.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from tw_ml.datagen.alloc import stratified_sample
from tw_ml.datagen.hardset import TEMPLATE_ID as HARD_SET_TEMPLATE_ID
from tw_ml.datagen.records import TicketPayload
from tw_ml.datagen.text import content_sha256

MANIFEST_VERSION: Final = "manifest.v1"
VAL_DEV_SIZE: Final = 225
VAL_DEV_SEED: Final = 20260927


class ManifestError(RuntimeError):
    """Raised when a frozen manifest would change or a file cannot be read."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileEntry(_Model):
    """One hashed data file."""

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)
    records: int = Field(ge=0)


class Manifest(_Model):
    """A split version's manifest."""

    manifest_version: str = MANIFEST_VERSION
    split: str
    dataset_version: str = Field(pattern=r"^v\d+$")
    created_at: AwareDatetime
    frozen: bool = False
    frozen_at: AwareDatetime | None = None
    taxonomy_version: str | None = None
    files: tuple[FileEntry, ...]
    records: int = Field(ge=0)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    generator_families: dict[str, int] = Field(default_factory=dict)
    label_sources: dict[str, int] = Field(default_factory=dict)
    subsets: dict[str, list[str]] = Field(default_factory=dict)
    subset_seeds: dict[str, int] = Field(default_factory=dict)
    notes: str = ""


def _rows(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return [_owner_row(r) if _is_owner_row(r) else r for r in rows if not _is_template(r)]


def _is_template(row: Mapping[str, Any]) -> bool:
    return row.get("record_id") == HARD_SET_TEMPLATE_ID and "provenance" not in row


def _is_owner_row(row: Mapping[str, Any]) -> bool:
    return "provenance" not in row and "attestation" in row and "ticket" in row


def _owner_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Identity of an owner-written hard-set row (``evals/hard_set.v1.jsonl`` format)."""
    ticket = TicketPayload.model_validate(row["ticket"])
    return {
        "record_id": row.get("record_id"),
        "content_sha256": content_sha256(ticket.customer_text()),
        "generator_family": "human",
        "label_source": "human_written",
    }


def record_key(row: Mapping[str, Any]) -> tuple[str, str]:
    """``(record_id, content_sha256)`` of a record row or a pointer row.

    Args:
        row: Parsed JSONL row (``provenance`` block or top-level fields).

    Returns:
        The identity pair.

    Raises:
        ManifestError: If the row carries neither shape.
    """
    source = row.get("provenance", row)
    record_id, digest = source.get("record_id"), source.get("content_sha256")
    if not isinstance(record_id, str) or not isinstance(digest, str):
        msg = "row lacks record_id/content_sha256"
        raise ManifestError(msg)
    return record_id, digest


def content_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    """Order-independent digest of a split's records.

    Args:
        rows: Parsed rows.

    Returns:
        SHA-256 over the sorted ``record_id:content_sha256`` lines.
    """
    lines = sorted(f"{rid}:{digest}" for rid, digest in (record_key(r) for r in rows))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def build_manifest(
    split: str,
    files: Sequence[Path],
    repo_root: Path,
    *,
    now: datetime,
    version: str = "v1",
    subsets: Mapping[str, Sequence[str]] | None = None,
    subset_seeds: Mapping[str, int] | None = None,
) -> Manifest:
    """Hash a split's files and summarize its records.

    Args:
        split: Split name.
        files: JSONL files (records or pointers).
        repo_root: Repository root (paths are stored relative to it).
        now: Creation time.
        version: Dataset version (``v1``...).
        subsets: Named subsets of record ids.
        subset_seeds: Seeds used to draw the subsets.

    Returns:
        The manifest (not frozen).

    Raises:
        ManifestError: If a file is missing.
    """
    entries: list[FileEntry] = []
    rows: list[dict[str, Any]] = []
    for path in files:
        if not path.is_file():
            msg = f"missing data file: {path.name}"
            raise ManifestError(msg)
        file_rows = _rows(path)
        rows.extend(file_rows)
        entries.append(
            FileEntry(
                path=_relative(path, repo_root),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size,
                records=len(file_rows),
            )
        )
    provenance = [r.get("provenance", r) for r in rows]
    taxonomy = sorted(
        {str(p.get("taxonomy_version")) for p in provenance if p.get("taxonomy_version")}
    )
    return Manifest(
        split=split,
        dataset_version=version,
        created_at=now,
        taxonomy_version=taxonomy[0] if len(taxonomy) == 1 else None,
        files=tuple(entries),
        records=len(rows),
        content_digest=content_digest(rows),
        generator_families=dict(
            sorted(
                Counter(str(p.get("generator_family", "public_bitext")) for p in provenance).items()
            )
        ),
        label_sources=dict(
            sorted(Counter(str(p.get("label_source", "")) for p in provenance).items())
        ),
        subsets={k: sorted(v) for k, v in (subsets or {}).items()},
        subset_seeds=dict(subset_seeds or {}),
    )


def verify_manifest(manifest: Manifest, repo_root: Path) -> list[str]:
    """Check files and records against a manifest.

    Args:
        manifest: Manifest to verify.
        repo_root: Repository root.

    Returns:
        Problems (empty when everything matches).
    """
    problems: list[str] = []
    rows: list[dict[str, Any]] = []
    for entry in manifest.files:
        path = repo_root / entry.path
        if not path.is_file():
            problems.append(f"missing file {entry.path}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.sha256:
            problems.append(f"sha256 mismatch for {entry.path}")
        rows.extend(_rows(path))
    if not problems:
        if len(rows) != manifest.records:
            problems.append(f"record count {len(rows)} != {manifest.records}")
        if content_digest(rows) != manifest.content_digest:
            problems.append("content digest mismatch")
    ids = {record_key(r)[0] for r in rows} if not problems else set()
    for name, members in manifest.subsets.items():
        if ids and not set(members) <= ids:
            problems.append(f"subset {name} names unknown records")
    return problems


def manifest_path(manifests_dir: Path, split: str) -> Path:
    """Where a split's current manifest lives.

    Args:
        manifests_dir: ``data/manifests``.
        split: Split.

    Returns:
        ``<dir>/<split>.json``.
    """
    return manifests_dir / f"{split}.json"


def load_manifest(path: Path) -> Manifest:
    """Read a manifest.

    Args:
        path: Manifest file.

    Returns:
        The manifest.
    """
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: Manifest) -> None:
    """Write a manifest (pretty JSON, LF).

    Args:
        path: Destination.
        manifest: Manifest.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def freeze(path: Path, manifest: Manifest, *, now: datetime, bump: bool = False) -> Manifest:
    """Freeze a split: write the manifest as immutable (or version it after a change).

    Args:
        path: ``data/manifests/<split>.json``.
        manifest: Freshly built manifest of the current content.
        now: Freeze time.
        bump: Allow new content by archiving the frozen manifest and writing the next version.

    Returns:
        The frozen manifest that was written (or the unchanged existing one).

    Raises:
        ManifestError: If a frozen manifest exists with different content and ``bump`` is False.
    """
    if path.is_file():
        current = load_manifest(path)
        if current.frozen:
            if (
                current.content_digest == manifest.content_digest
                and current.files == manifest.files
            ):
                return current
            if not bump:
                name = f"{current.split} {current.dataset_version}"
                msg = f"{name} is frozen; changes need a new version (--bump)"
                raise ManifestError(msg)
            archive = path.with_name(f"{current.split}.{current.dataset_version}.json")
            write_manifest(archive, current)
            number = int(current.dataset_version[1:]) + 1
            manifest = manifest.model_copy(update={"dataset_version": f"v{number}"})
    frozen = manifest.model_copy(update={"frozen": True, "frozen_at": now})
    write_manifest(path, frozen)
    return frozen


def val_dev_subset(
    rows: Sequence[Mapping[str, Any]], seed: int = VAL_DEV_SEED, size: int = VAL_DEV_SIZE
) -> list[str]:
    """``val_dev``: a fixed, stratified 50% subset of val (225 records; lead confirmation 4).

    Args:
        rows: Parsed val rows.
        seed: Seed (recorded in the manifest).
        size: Subset size.

    Returns:
        Record ids of the subset.
    """
    chosen = stratified_sample(
        list(rows),
        key=lambda r: str((r.get("labels") or {}).get("intent", "")),
        n=size,
        seed=seed,
        sort_key=lambda r: record_key(r)[0],
    )
    return sorted(record_key(r)[0] for r in chosen)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
