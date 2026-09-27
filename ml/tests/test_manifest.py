"""Content-hash manifests: build, verify, tamper detection, freeze immutability, versioning."""

import json
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.manifest import (
    ManifestError,
    build_manifest,
    content_digest,
    freeze,
    load_manifest,
    manifest_path,
    record_key,
    val_dev_subset,
    verify_manifest,
    write_manifest,
)
from tw_ml.datagen.records import DatasetRecord, TicketPayload

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
Writer = Callable[[Path, list[Any]], Path]


@pytest.fixture
def split_file(
    tmp_path: Path,
    write_jsonl: Writer,
    make_record: Callable[..., DatasetRecord],
    make_ticket: Callable[..., TicketPayload],
) -> Path:
    rows = [
        json.loads(
            make_record(
                ticket=make_ticket(message=f"Okta fails with SAML_ERR_302 for team {i}."),
                record_id=f"tr_{i:05d}",
            ).model_dump_json()
        )
        for i in range(6)
    ]
    return write_jsonl(tmp_path / "data" / "train.jsonl", rows)


def test_build_and_verify(split_file: Path, tmp_path: Path) -> None:
    manifest = build_manifest(
        "train",
        [split_file],
        tmp_path,
        now=NOW,
        subsets={"sample": ["tr_00002", "tr_00001"]},
        subset_seeds={"sample": 3},
    )
    assert manifest.records == 6
    assert manifest.files[0].path == "data/train.jsonl"
    assert manifest.files[0].records == 6
    assert manifest.generator_families == {"openai_gpt_oss": 6}
    assert manifest.label_sources == {"generator_proposed": 6}
    assert manifest.taxonomy_version == "2026-09-v1"
    assert manifest.subsets == {"sample": ["tr_00001", "tr_00002"]}
    assert not manifest.frozen
    assert verify_manifest(manifest, tmp_path) == []


def test_digest_ignores_order_but_not_content(split_file: Path) -> None:
    rows = [json.loads(line) for line in split_file.read_text(encoding="utf-8").splitlines()]
    assert content_digest(rows) == content_digest(list(reversed(rows)))
    changed = json.loads(json.dumps(rows))
    changed[0]["provenance"]["content_sha256"] = "0" * 64
    assert content_digest(changed) != content_digest(rows)
    assert record_key({"record_id": "to_0001", "content_sha256": "a" * 64}) == ("to_0001", "a" * 64)
    with pytest.raises(ManifestError, match="record_id"):
        record_key({"nothing": 1})


def test_verify_detects_tampering(split_file: Path, tmp_path: Path) -> None:
    manifest = build_manifest(
        "train", [split_file], tmp_path, now=NOW, subsets={"sample": ["tr_00001"]}
    )
    original = split_file.read_text(encoding="utf-8")
    split_file.write_text(original.replace("team 3", "team 9"), encoding="utf-8")
    assert "sha256 mismatch for data/train.jsonl" in verify_manifest(manifest, tmp_path)
    split_file.write_text(original, encoding="utf-8")
    ghost = manifest.model_copy(update={"subsets": {"sample": ["tr_99999"]}})
    assert verify_manifest(ghost, tmp_path) == ["subset sample names unknown records"]
    split_file.unlink()
    assert verify_manifest(manifest, tmp_path) == ["missing file data/train.jsonl"]
    with pytest.raises(ManifestError, match="missing data file"):
        build_manifest("train", [split_file], tmp_path, now=NOW)


def test_count_and_digest_mismatch(split_file: Path, tmp_path: Path) -> None:
    manifest = build_manifest("train", [split_file], tmp_path, now=NOW)
    wrong_count = manifest.model_copy(update={"records": 7})
    assert "record count 6 != 7" in verify_manifest(wrong_count, tmp_path)
    wrong_digest = manifest.model_copy(update={"content_digest": "f" * 64})
    assert "content digest mismatch" in verify_manifest(wrong_digest, tmp_path)


def test_freeze_is_immutable_until_a_version_bump(split_file: Path, tmp_path: Path) -> None:
    target = manifest_path(tmp_path / "manifests", "train")
    first = freeze(target, build_manifest("train", [split_file], tmp_path, now=NOW), now=NOW)
    assert first.frozen
    assert first.frozen_at == NOW
    assert first.dataset_version == "v1"
    again = freeze(target, build_manifest("train", [split_file], tmp_path, now=NOW), now=NOW)
    assert again == first  # same content: nothing changes
    split_file.write_text(
        split_file.read_text(encoding="utf-8").replace("team 1", "team 7"), encoding="utf-8"
    )
    changed = build_manifest("train", [split_file], tmp_path, now=NOW)
    with pytest.raises(ManifestError, match="frozen"):
        freeze(target, changed, now=NOW)
    bumped = freeze(target, changed, now=NOW, bump=True)
    assert bumped.dataset_version == "v2"
    assert load_manifest(target) == bumped
    assert load_manifest(target.with_name("train.v1.json")) == first


def test_write_and_load_round_trip(split_file: Path, tmp_path: Path) -> None:
    manifest = build_manifest("train", [split_file], tmp_path, now=NOW)
    path = tmp_path / "m" / "train.json"
    write_manifest(path, manifest)
    assert load_manifest(path) == manifest
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_val_dev_is_a_fixed_stratified_half() -> None:
    rows = [
        {
            "provenance": {"record_id": f"va_{i:05d}", "content_sha256": "0" * 64},
            "labels": {"intent": intent},
        }
        for i, intent in enumerate(["bug_report"] * 300 + ["security_report"] * 150)
    ]
    subset = val_dev_subset(rows)
    assert len(subset) == 225
    assert subset == val_dev_subset(list(reversed(rows)))
    intents = Counter(rows[int(rid[3:])]["labels"]["intent"] for rid in subset)
    assert intents == {"bug_report": 150, "security_report": 75}
    assert val_dev_subset(rows, seed=1) != subset


def test_absolute_paths_outside_the_root(split_file: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "root"
    elsewhere.mkdir()
    manifest = build_manifest("train", [split_file], elsewhere, now=NOW)
    assert Path(manifest.files[0].path).is_absolute()
    assert verify_manifest(manifest, elsewhere) == []


def test_owner_written_hard_set_rows(
    tmp_path: Path, write_jsonl: Writer, hard_cases: list[dict[str, Any]], paths: Any
) -> None:
    template = json.loads(
        (paths.root / "data" / "hard_set" / "TEMPLATE.jsonl").read_text(encoding="utf-8")
    )
    source = write_jsonl(tmp_path / "evals" / "hard_set.v1.jsonl", [template, *hard_cases[:5]])
    manifest = build_manifest("test_hard", [source], tmp_path, now=NOW)
    assert manifest.records == 5  # the template row never counts
    assert manifest.generator_families == {"human": 5}
    assert manifest.label_sources == {"human_written": 5}
    assert verify_manifest(manifest, tmp_path) == []
    edited = json.loads(json.dumps(hard_cases[:5]))
    edited[0]["ticket"]["message"] += " Edited."
    write_jsonl(source, [template, *edited])
    assert "sha256 mismatch for evals/hard_set.v1.jsonl" in verify_manifest(manifest, tmp_path)
    assert (
        content_digest([{"record_id": "th_001", "content_sha256": "0" * 64}])
        != manifest.content_digest
    )
