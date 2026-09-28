"""Holdout guard: sealed splits stay sealed until P10 (spec v1.1 §9.3, §9.8, §16; A-10).

Sealed splits are ``test_synth``, ``hard_final`` (and therefore the whole ``test_hard``),
``test_ood``, ``e2e_scenarios`` and ``qrels_test``. Before P10 nothing may evaluate them:
thresholds, prompts, calibration, seeds and error analysis use ``val`` / ``val_dev`` /
``hard_dev`` / ``qrels_dev`` only. The guard does not trust the ``--split`` name alone. It
derives each gold record's origin from ``provenance.split`` or its record-id prefix (``ts_``,
``th_``, ``to_``, ``te_``...), maps ``test_hard`` records to ``hard_dev`` only when the frozen
``data/manifests/test_hard.json`` lists them in its ``hard_dev`` subset (otherwise they count
as ``hard_final``), and refuses records it cannot place.

A sealed evaluation needs ``--phase P10`` **and** ``--i-understand-sealed``; each one is appended
to ``evals/sealed_access.jsonl`` with its hashes and the running ``eval_count_on_split`` that
every report publishes (protected splits are evaluated once per registered model version).
"""

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from tw_ml.datagen.manifest import load_manifest
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import SPLIT_CODES

OPEN_SPLITS: Final[tuple[str, ...]] = ("train", "val", "val_dev", "hard_dev", "qrels_dev", "smoke")
SEALED_SPLITS: Final[tuple[str, ...]] = (
    "test_synth",
    "hard_final",
    "test_hard",
    "test_ood",
    "e2e_scenarios",
    "qrels_test",
)
UNSEAL_PHASE: Final = "P10"
UNKNOWN: Final = "unknown"
ALLOWED_ORIGINS: Final[Mapping[str, frozenset[str]]] = {
    "train": frozenset({"train"}),
    "val": frozenset({"val"}),
    "val_dev": frozenset({"val"}),
    "hard_dev": frozenset({"hard_dev"}),
    "qrels_dev": frozenset({"val"}),
    "smoke": frozenset({"train", "val", "hard_dev"}),
    "test_synth": frozenset({"test_synth"}),
    "hard_final": frozenset({"hard_final"}),
    "test_hard": frozenset({"hard_dev", "hard_final"}),
    "test_ood": frozenset({"test_ood"}),
    "e2e_scenarios": frozenset({"e2e_scenarios"}),
    "qrels_test": frozenset({"test_synth", "hard_dev", "hard_final"}),
}
"""Record origins each declared split may contain (``qrels_dev`` is built from val, LC-2)."""
_ORIGIN_BY_CODE: Final[Mapping[str, str]] = {code: split for split, code in SPLIT_CODES.items()}
_PREFIX: Final = re.compile(r"^([a-z]{2})_")


class HoldoutError(ValueError):
    """Raised when an evaluation request is inconsistent or unverifiable."""


class SealedSplitError(HoldoutError):
    """Raised when a sealed split would be evaluated without the P10 unseal flags."""


@dataclass(frozen=True, slots=True)
class SplitSubsets:
    """Named subsets from the frozen manifests.

    Attributes:
        hard_dev: ``hard_dev`` ids of ``data/manifests/test_hard.json`` (``None`` if absent).
        val_dev: ``val_dev`` ids of ``data/manifests/val.json`` (``None`` if absent).
    """

    hard_dev: frozenset[str] | None = None
    val_dev: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class AccessDecision:
    """An authorized evaluation.

    Attributes:
        split: Declared split (``None`` for a prediction run without one).
        sealed: Whether sealed data is involved (only possible in P10 with the flag).
        phase: Declared phase.
        origins: Effective record origin to count.
        notes: Caveats (unverified subsets...).
    """

    split: str | None
    sealed: bool
    phase: str
    origins: Mapping[str, int]
    notes: tuple[str, ...] = field(default=())


def infer_origin(record_id: str, provenance_split: str | None = None) -> str | None:
    """Origin split of a record: its provenance, else its record-id prefix.

    Args:
        record_id: Record id (``va_00001``, ``th_012``...).
        provenance_split: ``provenance.split`` when the row has one.

    Returns:
        The split name, or ``None`` when neither source identifies it.
    """
    if provenance_split:
        return provenance_split
    match = _PREFIX.match(record_id)
    return _ORIGIN_BY_CODE.get(match.group(1)) if match else None


def effective_split(record_id: str, origin: str | None, subsets: SplitSubsets) -> str:
    """Where a record sits for holdout purposes.

    ``test_hard`` records are ``hard_dev`` only when the manifest lists them there; everything
    else from the hard set is treated as ``hard_final`` (sealed), so a missing manifest fails
    closed.

    Args:
        record_id: Record id.
        origin: Its origin split (see :func:`infer_origin`).
        subsets: Manifest subsets.

    Returns:
        ``train``, ``val``, ``hard_dev``, ``hard_final``, a protected split name, or ``unknown``.
    """
    if origin == "test_hard":
        in_dev = subsets.hard_dev is not None and record_id in subsets.hard_dev
        return "hard_dev" if in_dev else "hard_final"
    return origin or UNKNOWN


def _subset(path: Path, name: str) -> frozenset[str] | None:
    if not path.is_file():
        return None
    try:
        members = load_manifest(path).subsets.get(name)
    except ValueError as exc:  # pydantic.ValidationError included
        msg = f"manifest {path.name} is unreadable ({type(exc).__name__}); refusing to guess"
        raise HoldoutError(msg) from None
    return frozenset(members) if members is not None else None


def load_subsets(paths: RepoPaths) -> SplitSubsets:
    """Read the ``hard_dev`` and ``val_dev`` subsets from the committed manifests.

    Args:
        paths: Repository paths.

    Returns:
        The subsets (``None`` where a manifest or subset is absent).
    """
    return SplitSubsets(
        hard_dev=_subset(paths.manifests_dir / "test_hard.json", "hard_dev"),
        val_dev=_subset(paths.manifests_dir / "val.json", "val_dev"),
    )


def authorize(
    split: str | None,
    records: Iterable[tuple[str, str | None]],
    *,
    phase: str,
    i_understand_sealed: bool,
    subsets: SplitSubsets,
) -> AccessDecision:
    """Decide whether an evaluation may run.

    Args:
        split: Declared split (``None`` when only the records decide, e.g. a prediction run).
        records: ``(record_id, provenance_split)`` of every gold or input record.
        phase: Declared project phase (``P2``...).
        i_understand_sealed: The explicit unseal acknowledgement.
        subsets: Manifest subsets.

    Returns:
        The decision.

    Raises:
        HoldoutError: If the split is unknown, a record's origin cannot be verified, the records
            do not belong to the declared split, or the unseal flag is used outside P10.
        SealedSplitError: If sealed data is involved without ``phase == "P10"`` and the flag.
    """
    if split is not None and split not in ALLOWED_ORIGINS:
        msg = f"unknown split {split!r}; expected one of {', '.join(ALLOWED_ORIGINS)}"
        raise HoldoutError(msg)
    if i_understand_sealed and phase != UNSEAL_PHASE:
        msg = f"--i-understand-sealed is only valid with --phase {UNSEAL_PHASE}"
        raise HoldoutError(msg)
    placed = [
        (rid, effective_split(rid, infer_origin(rid, prov), subsets)) for rid, prov in records
    ]
    origins = Counter(where for _, where in placed)
    if origins.get(UNKNOWN):
        msg = (
            f"{origins[UNKNOWN]} records have no recognizable origin (provenance.split or a "
            "known record-id prefix); refusing to evaluate unverifiable data"
        )
        raise HoldoutError(msg)
    sealed_found = sorted(where for where in origins if where in SEALED_SPLITS)
    sealed = bool(sealed_found) or (split is not None and split in SEALED_SPLITS)
    if sealed and not (phase == UNSEAL_PHASE and i_understand_sealed):
        named = ", ".join(f"{where} ({origins[where]})" for where in sealed_found) or split
        hint = (
            " (no hard_dev subset in data/manifests/test_hard.json: every test_hard record is "
            "treated as hard_final)"
            if "hard_final" in sealed_found and subsets.hard_dev is None
            else ""
        )
        msg = (
            f"refusing to evaluate sealed data: {named}{hint}. Sealed splits stay untouched "
            f"until {UNSEAL_PHASE}; pass --phase {UNSEAL_PHASE} --i-understand-sealed only for "
            "the pre-registered P10 run (logged to evals/sealed_access.jsonl)"
        )
        raise SealedSplitError(msg)
    notes: list[str] = []
    if split is not None:
        unexpected = sorted(set(origins) - ALLOWED_ORIGINS[split])
        if unexpected:
            msg = f"declared split {split!r} but records come from: {', '.join(unexpected)}"
            raise HoldoutError(msg)
        if split == "val_dev":
            notes.extend(_check_val_dev(placed, subsets))
    return AccessDecision(split, sealed, phase, dict(sorted(origins.items())), tuple(notes))


def _check_val_dev(placed: list[tuple[str, str]], subsets: SplitSubsets) -> list[str]:
    if subsets.val_dev is None:
        return ["val_dev membership not verified (no val_dev subset in data/manifests/val.json)"]
    outside = [rid for rid, _ in placed if rid not in subsets.val_dev]
    if outside:
        msg = f"{len(outside)} records are not in the val_dev subset of data/manifests/val.json"
        raise HoldoutError(msg)
    return []


@dataclass(frozen=True, slots=True)
class SealedAccess:
    """One sealed-split access, as appended to ``evals/sealed_access.jsonl``.

    Attributes:
        at: When.
        action: ``score``, ``compare`` or ``predict``.
        split: Declared split (or the sealed origins of a prediction run).
        system_id: System evaluated.
        experiment: Experiment id, if any.
        phase: Phase (always ``P10``).
        gold_sha256: Gold (or input) file hash.
        predictions_sha256: Prediction file hashes.
        git_sha: Commit, when known.
        n_records: Records involved.
    """

    at: datetime
    action: str
    split: str
    system_id: str
    experiment: str | None
    phase: str
    gold_sha256: str
    predictions_sha256: tuple[str, ...]
    git_sha: str | None
    n_records: int


def _read_log(log_file: Path) -> list[dict[str, Any]]:
    if not log_file.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(log_file.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = None
        if not isinstance(row, dict):
            msg = f"{log_file.name} line {number} is corrupt; the access log must stay intact"
            raise HoldoutError(msg)
        rows.append(row)
    return rows


def eval_count(log_file: Path, *, split: str, system_id: str, action: str = "score") -> int:
    """Number of logged sealed evaluations of one system on one split.

    Args:
        log_file: ``evals/sealed_access.jsonl``.
        split: Split.
        system_id: System id.
        action: Logged action to count.

    Returns:
        The count (0 when the log does not exist).
    """
    return sum(
        1
        for row in _read_log(log_file)
        if row.get("split") == split
        and row.get("system_id") == system_id
        and row.get("action") == action
    )


def log_sealed_access(log_file: Path, access: SealedAccess) -> int:
    """Append a sealed access and return the running ``eval_count_on_split``.

    Args:
        log_file: ``evals/sealed_access.jsonl`` (created on first use).
        access: The access.

    Returns:
        The count of this system's logged accesses on this split, including this one.
    """
    count = 1 + eval_count(
        log_file, split=access.split, system_id=access.system_id, action=access.action
    )
    row = {
        "at": access.at.isoformat(timespec="seconds"),
        "action": access.action,
        "split": access.split,
        "system_id": access.system_id,
        "experiment": access.experiment,
        "phase": access.phase,
        "gold_sha256": access.gold_sha256,
        "predictions_sha256": list(access.predictions_sha256),
        "git_sha": access.git_sha,
        "n_records": access.n_records,
        "eval_count_on_split": count,
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return count
