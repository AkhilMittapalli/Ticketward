"""tw_ml.eval.holdout: sealed splits are refused before P10, and every sealed access is logged."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tw_ml.datagen.manifest import Manifest, write_manifest
from tw_ml.datagen.paths import RepoPaths
from tw_ml.eval.holdout import (
    SEALED_SPLITS,
    AccessDecision,
    HoldoutError,
    SealedAccess,
    SealedSplitError,
    SplitSubsets,
    authorize,
    effective_split,
    eval_count,
    infer_origin,
    load_subsets,
    log_sealed_access,
)

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
OPEN = SplitSubsets()
HARD = SplitSubsets(hard_dev=frozenset({"th_001", "th_002"}))


def _ok(
    split: str | None,
    ids: list[str],
    *,
    phase: str = "P2",
    i_understand_sealed: bool = False,
    subsets: SplitSubsets = OPEN,
) -> AccessDecision:
    return authorize(
        split,
        [(rid, None) for rid in ids],
        phase=phase,
        i_understand_sealed=i_understand_sealed,
        subsets=subsets,
    )


def test_origin_inference() -> None:
    assert infer_origin("va_00001") == "val"
    assert infer_origin("ts_00001") == "test_synth"
    assert infer_origin("th_012") == "test_hard"
    assert infer_origin("to_1") == "test_ood"
    assert infer_origin("te_1") == "e2e_scenarios"
    assert infer_origin("xx_1") is None
    assert infer_origin("va_1", "test_synth") == "test_synth"  # provenance wins over the prefix
    assert effective_split("th_001", "test_hard", HARD) == "hard_dev"
    assert effective_split("th_050", "test_hard", HARD) == "hard_final"
    assert effective_split("th_001", "test_hard", OPEN) == "hard_final"  # no manifest: sealed


def test_open_splits_are_allowed() -> None:
    decision = authorize(
        "val",
        [("va_1", "val"), ("va_2", None)],
        phase="P2",
        i_understand_sealed=False,
        subsets=OPEN,
    )
    assert not decision.sealed
    assert decision.origins == {"val": 2}
    hard = authorize(
        "hard_dev", [("th_001", None)], phase="P2", i_understand_sealed=False, subsets=HARD
    )
    assert hard.origins == {"hard_dev": 1}
    assert not authorize(
        None, [("tr_1", None), ("va_1", None)], phase="P2", i_understand_sealed=False, subsets=OPEN
    ).sealed


@pytest.mark.parametrize("split", SEALED_SPLITS)
def test_every_sealed_split_name_is_refused_before_p10(split: str) -> None:
    with pytest.raises(SealedSplitError, match="refusing to evaluate sealed data"):
        _ok(split, ["va_1"])


def test_sealed_records_under_an_open_name_are_refused() -> None:
    with pytest.raises(SealedSplitError, match=r"test_synth \(2\)"):
        _ok("val", ["va_1", "ts_1", "ts_2"])
    with pytest.raises(SealedSplitError, match="no hard_dev subset"):
        _ok("hard_dev", ["th_001"])
    with pytest.raises(SealedSplitError, match="hard_final"):
        _ok("hard_dev", ["th_001", "th_099"], subsets=HARD)
    with pytest.raises(SealedSplitError):
        _ok(None, ["te_1"])


def test_unseal_needs_both_p10_and_the_flag() -> None:
    with pytest.raises(SealedSplitError):
        _ok("test_synth", ["ts_1"], phase="P10")
    with pytest.raises(HoldoutError, match="only valid with --phase P10"):
        _ok("test_synth", ["ts_1"], phase="P9", i_understand_sealed=True)
    decision = _ok("test_synth", ["ts_1"], phase="P10", i_understand_sealed=True)
    assert decision.sealed
    assert decision.phase == "P10"


def test_inconsistent_or_unverifiable_requests_are_refused() -> None:
    with pytest.raises(HoldoutError, match="unknown split"):
        _ok("test", ["va_1"])
    with pytest.raises(HoldoutError, match="no recognizable origin"):
        _ok("val", ["va_1", "rec_7"])
    with pytest.raises(HoldoutError, match="records come from: train"):
        _ok("val", ["va_1", "tr_1"])


def test_val_dev_membership() -> None:
    unverified = _ok("val_dev", ["va_1"])
    assert "not verified" in unverified.notes[0]
    subsets = SplitSubsets(val_dev=frozenset({"va_1"}))
    assert _ok("val_dev", ["va_1"], subsets=subsets).notes == ()
    with pytest.raises(HoldoutError, match="not in the val_dev subset"):
        _ok("val_dev", ["va_1", "va_2"], subsets=subsets)


def _manifest(split: str, subsets: dict[str, list[str]]) -> Manifest:
    return Manifest(
        split=split,
        dataset_version="v1",
        created_at=NOW,
        files=(),
        records=0,
        content_digest="0" * 64,
        subsets=subsets,
    )


def test_subsets_come_from_the_frozen_manifests(tmp_path: Path) -> None:
    paths = RepoPaths(tmp_path)
    assert load_subsets(paths) == SplitSubsets()
    write_manifest(
        paths.manifests_dir / "test_hard.json", _manifest("test_hard", {"hard_dev": ["th_001"]})
    )
    write_manifest(paths.manifests_dir / "val.json", _manifest("val", {}))
    assert load_subsets(paths) == SplitSubsets(hard_dev=frozenset({"th_001"}), val_dev=None)
    (paths.manifests_dir / "val.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(HoldoutError, match="unreadable"):
        load_subsets(paths)


def _access(system_id: str = "sys", split: str = "test_synth") -> SealedAccess:
    return SealedAccess(
        at=NOW,
        action="score",
        split=split,
        system_id=system_id,
        experiment="E4",
        phase="P10",
        gold_sha256="a" * 64,
        predictions_sha256=("b" * 64,),
        git_sha=None,
        n_records=3,
    )


def test_sealed_access_log_counts_per_system_and_split(tmp_path: Path) -> None:
    log = tmp_path / "evals" / "sealed_access.jsonl"
    assert eval_count(log, split="test_synth", system_id="sys") == 0
    assert log_sealed_access(log, _access()) == 1
    assert log_sealed_access(log, _access()) == 2
    assert log_sealed_access(log, _access(system_id="other")) == 1
    assert log_sealed_access(log, _access(split="hard_final")) == 1
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["eval_count_on_split"] for r in rows] == [1, 2, 1, 1]
    assert rows[0]["at"] == "2026-09-27T12:00:00+00:00"
    log.write_text(log.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    with pytest.raises(HoldoutError, match="corrupt"):
        log_sealed_access(log, _access())
