"""Option A SFT rows and guarded train/val loading (tw_ml.train.data; spec §9.4, S-12).

A fake ChatML tokenizer (conftest ``FakeSFTTokenizer``) stands in for the Hugging Face one, so
the parity, boundary, EOS and length checks run offline.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.manifest import build_manifest, write_manifest
from tw_ml.datagen.records import DatasetRecord
from tw_ml.export.prompt_format import PromptFormat, derive_prompt_format
from tw_ml.prompts import TriagePrompt, derive_nonce, load_triage_prompt
from tw_ml.train.data import (
    IGNORE_INDEX,
    DataManifest,
    ParityError,
    ProvenanceError,
    SFTSplit,
    TokenizationError,
    TrainingDataError,
    build_sft_split,
    chat_prompt_text,
    check_length_budget,
    forbidden_vendor_fields,
    gold_items,
    load_split,
    load_training_data,
    nonce_salt,
    render_split,
    rows_sha256,
    split_manifest,
    split_summary,
    write_data_manifest,
)

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
SALT = "sft.v1:sft-test:seed42"
CHAR_BUDGET = 100_000
"""The fake tokenizer is character-level: real rows fit 2,048 tokens, these need more."""
Tokenizer = Any  # conftest FakeSFTTokenizer (fixtures cannot be imported as types)


@pytest.fixture(scope="module")
def prompt() -> TriagePrompt:
    return load_triage_prompt()


@pytest.fixture
def tokenizer(make_sft_tokenizer: Callable[..., Tokenizer]) -> Tokenizer:
    return make_sft_tokenizer()


@pytest.fixture
def fmt(tokenizer: Tokenizer) -> PromptFormat:
    return derive_prompt_format(tokenizer, base_model="Qwen/Qwen3.5-2B", base_revision="b" * 40)


def _write(path: Path, rows: list[Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r) for r in rows]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def _rows(records: list[DatasetRecord]) -> list[Any]:
    return [json.loads(r.model_dump_json()) for r in records]


def _build(
    split: Any, tokenizer: Tokenizer, prompt: TriagePrompt, fmt: PromptFormat, **kw: Any
) -> SFTSplit:
    options = {"salt": SALT, "max_length": CHAR_BUDGET, **kw}
    return build_sft_split(split, tokenizer=tokenizer, prompt=prompt, fmt=fmt, **options)


def test_rows_mask_the_prompt_and_train_on_target_plus_eos(
    write_train_data: Callable[..., Path],
    train_paths: Any,
    tokenizer: Tokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    split = _build(data.train, tokenizer, prompt, fmt)
    assert len(split.rows) == len(data.train.records) == 6
    assert split.rejected_over_length == ()
    for row, record, rendered in zip(
        split.rows, data.train.records, render_split(data.train, prompt, fmt, SALT), strict=True
    ):
        text = chat_prompt_text(tokenizer, rendered)
        assert text.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
        prompt_ids = tokenizer.encode(text)
        completion_ids = tokenizer.encode(f"{record.labels.model_dump_json()}<|im_end|>")
        assert list(row.input_ids) == prompt_ids + completion_ids
        assert list(row.labels) == [IGNORE_INDEX] * len(prompt_ids) + completion_ids
        assert row.prompt_tokens == len(prompt_ids)
        assert row.completion_tokens == len(completion_ids)
        assert completion_ids[-1] == tokenizer.eos_token_id
        features = row.features()
        assert features["completion_mask"] == [0] * len(prompt_ids) + [1] * len(completion_ids)
        assert split.prompts[record.record_id] == tuple(prompt_ids)
    assert split.stats.rows == 6
    assert split.stats.total_max == max(len(r.input_ids) for r in split.rows)


def test_prompts_use_the_derived_nonce_and_the_format_special_tokens(
    write_train_data: Callable[..., Path], train_paths: Any, prompt: TriagePrompt, fmt: PromptFormat
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    rendered = render_split(data.val, prompt, fmt, SALT)
    assert [r.nonce for r in rendered] == [
        derive_nonce(rid, salt=SALT) for rid in data.val.record_ids
    ]
    assert nonce_salt("sft.v1", "sft-x", 42) != nonce_salt("sft.v1", "sft-x", 1337)
    assert all(r.target is not None for r in rendered)


def test_parity_failure_lists_record_ids(
    write_train_data: Callable[..., Path],
    train_paths: Any,
    tokenizer: Tokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    drifted = fmt.model_copy(update={"system_prefix": "<|im_start|>system \n"})
    with pytest.raises(ParityError, match="differs from render_raw for tr_00001, tr_00002"):
        _build(data.train, tokenizer, prompt, drifted)


def test_boundary_merge_is_a_hard_failure(
    write_train_data: Callable[..., Path],
    train_paths: Any,
    make_sft_tokenizer: Callable[..., Tokenizer],
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    merging = make_sft_tokenizer(
        merge="\n{"
    )  # "...</think>\n\n" + "{..." fuses across the boundary
    with pytest.raises(TokenizationError, match="joint and concatenated tokenization differ"):
        _build(data.train, merging, prompt, fmt)


def test_eos_inside_the_target_is_refused(
    tmp_path: Path,
    make_split_records: Callable[..., list[DatasetRecord]],
    make_labels: Callable[..., Any],
    train_paths: Any,
    tokenizer: Tokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    record = make_split_records("train", 1)[0]
    poisoned = record.model_copy(
        update={"labels": make_labels(rationale="ends early <|im_end|> here")}
    )
    path = _write(tmp_path / "train" / "records.jsonl", _rows([poisoned]))
    split = load_split(path, "train", train_paths)
    with pytest.raises(TokenizationError, match="only EOS for tr_00001"):
        _build(split, tokenizer, prompt, fmt)


def test_eos_must_be_a_serving_stop(
    write_train_data: Callable[..., Path],
    train_paths: Any,
    tokenizer: Tokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    with pytest.raises(ParityError, match="is not a stop string"):
        _build(data.train, tokenizer, prompt, fmt.model_copy(update={"stop": ("<|endoftext|>",)}))
    with pytest.raises(TokenizationError, match="no EOS token"):
        _build(data.train, type(tokenizer)(eos_token=None), prompt, fmt)


def test_template_must_return_text(
    write_train_data: Callable[..., Path],
    train_paths: Any,
    tokenizer: Tokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    rendered = render_split(data.train, prompt, fmt, SALT)[0]

    class TokenIds(type(tokenizer)):  # type: ignore[misc]
        def apply_chat_template(
            self, conversation: list[dict[str, str]], **kwargs: object
        ) -> object:
            return [1, 2, 3]

    with pytest.raises(ParityError, match="did not return text"):
        chat_prompt_text(TokenIds(), rendered)


def test_rows_over_max_length_are_rejected_never_truncated(
    write_train_data: Callable[..., Path],
    train_paths: Any,
    tokenizer: Tokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    full = _build(data.train, tokenizer, prompt, fmt)
    lengths = sorted(len(r.input_ids) for r in full.rows)
    limit = lengths[-2]  # the longest row (at least) is over the budget
    capped = _build(data.train, tokenizer, prompt, fmt, max_length=limit)
    assert capped.rejected_over_length
    assert all(len(r.input_ids) <= limit for r in capped.rows)
    assert {r.record_id for r in capped.rows}.isdisjoint(capped.rejected_over_length)
    assert set(capped.prompts) == set(data.train.record_ids)  # generation eval keeps every record
    assert capped.rejected_fraction == pytest.approx(len(capped.rejected_over_length) / 6)
    check_length_budget(capped, 0.5)
    with pytest.raises(TrainingDataError, match="exceed max_length"):
        check_length_budget(capped, 0.01)
    none_left = _build(data.train, tokenizer, prompt, fmt, max_length=10)
    with pytest.raises(TrainingDataError, match="every row exceeds max_length"):
        check_length_budget(none_left, 1.0)


def test_vendor_markers_are_found_at_any_depth() -> None:
    assert forbidden_vendor_fields({"provider": "deepinfra", "notes": ["ok"]}) == []
    found = forbidden_vendor_fields(
        {
            "provider": "Anthropic",
            "bitext": {"dataset": "x"},
            "reviewed_by": ["R-1", "claude-sonnet-5"],
        }
    )
    assert found == ["provenance.provider", "provenance.reviewed_by.1"]
    assert forbidden_vendor_fields(None) == []


def test_anthropic_provenance_is_refused_before_validation(
    tmp_path: Path, make_split_records: Callable[..., list[DatasetRecord]], train_paths: Any
) -> None:
    rows = _rows(make_split_records("train", 3))
    rows[1]["provenance"]["label_notes"] = "relabelled with Claude"
    path = _write(tmp_path / "train" / "records.jsonl", rows)
    with pytest.raises(ProvenanceError, match=r"A-01, S-12\): line 2 \(provenance.label_notes\)"):
        load_split(path, "train", train_paths)


@pytest.mark.parametrize(
    ("builder", "fragment"),
    [
        ("sealed", "refusing to evaluate sealed data"),
        ("val_in_train", "records come from: val"),
        ("duplicate", "duplicate record ids"),
        ("invalid", "invalid record at"),
        ("empty", "has no records"),
    ],
)
def test_load_split_refusals(
    tmp_path: Path,
    make_split_records: Callable[..., list[DatasetRecord]],
    train_paths: Any,
    builder: str,
    fragment: str,
) -> None:
    rows = _rows(make_split_records("train", 2))
    if builder == "sealed":
        rows += _rows(make_split_records("test_synth", 1))
    elif builder == "val_in_train":
        rows += _rows(make_split_records("val", 1))
    elif builder == "duplicate":
        rows.append(rows[0])
    elif builder == "invalid":
        rows[0]["labels"]["intent"] = "not_an_intent"
    else:
        rows = []
    path = _write(tmp_path / "train" / "records.jsonl", rows)
    with pytest.raises(TrainingDataError, match=fragment):
        load_split(path, "train", train_paths)


def test_only_train_and_val_are_trainable(tmp_path: Path, train_paths: Any) -> None:
    with pytest.raises(TrainingDataError, match="only train, val may be trained on"):
        load_split(tmp_path / "x.jsonl", "test_synth", train_paths)  # type: ignore[arg-type]
    with pytest.raises(TrainingDataError, match=r"train data not found: train/records\.jsonl"):
        load_split(tmp_path / "train" / "records.jsonl", "train", train_paths)
    _write(tmp_path / "train" / "records.jsonl", ["{not json"])
    with pytest.raises(TrainingDataError, match="not valid JSON"):
        load_split(tmp_path / "train" / "records.jsonl", "train", train_paths)


def test_train_and_val_must_not_share_ids(
    tmp_path: Path, make_split_records: Callable[..., list[DatasetRecord]], train_paths: Any
) -> None:
    train = _rows(make_split_records("train", 2))
    _write(tmp_path / "train" / "records.jsonl", train)
    val = _rows(make_split_records("val", 1))
    val[0]["provenance"]["record_id"] = "va_00009"
    _write(tmp_path / "val" / "records.jsonl", val)
    loaded = load_training_data(tmp_path, "train/records.jsonl", "val/records.jsonl", train_paths)
    assert loaded.val.record_ids == ("va_00009",)
    val_as_train = train[:1]
    _write(tmp_path / "val" / "records.jsonl", val_as_train)
    with pytest.raises(TrainingDataError, match="records come from: train"):
        load_training_data(tmp_path, "train/records.jsonl", "val/records.jsonl", train_paths)


def test_committed_manifests_are_enforced(
    write_train_data: Callable[..., Path], train_paths: Any
) -> None:
    root = write_train_data()
    data = load_training_data(root, "train/records.jsonl", "val/records.jsonl", train_paths)
    assert dict(data.committed_manifests) == {"train": None, "val": None}
    manifest = build_manifest("train", [root / "train" / "records.jsonl"], root, now=NOW)
    write_manifest(train_paths.manifests_dir / "train.json", manifest)
    data = load_training_data(root, "train/records.jsonl", "val/records.jsonl", train_paths)
    manifest_bytes = (train_paths.manifests_dir / "train.json").read_bytes()
    assert data.committed_manifests["train"] == hashlib.sha256(manifest_bytes).hexdigest()
    other = build_manifest("val", [root / "val" / "records.jsonl"], root, now=NOW)
    write_manifest(
        train_paths.manifests_dir / "train.json", other.model_copy(update={"split": "train"})
    )
    with pytest.raises(TrainingDataError, match=r"differs from data/manifests/train\.json"):
        load_training_data(root, "train/records.jsonl", "val/records.jsonl", train_paths)
    (train_paths.manifests_dir / "train.json").write_text("{", encoding="utf-8")
    with pytest.raises(TrainingDataError, match="unreadable"):
        load_training_data(root, "train/records.jsonl", "val/records.jsonl", train_paths)


def test_manifest_digests_and_summaries(
    tmp_path: Path,
    write_train_data: Callable[..., Path],
    train_paths: Any,
    tokenizer: Tokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    split = _build(data.train, tokenizer, prompt, fmt)
    digest = rows_sha256(split.rows)
    assert digest == rows_sha256(list(split.rows))
    assert digest != rows_sha256(list(reversed(split.rows)))
    entry = split_manifest(data.train, None, rows=len(split.rows), token_stats={"total_max": 5.0})
    assert entry.generator_families == {"openai_gpt_oss": 6}
    assert entry.records == 6
    manifest = DataManifest(
        kind="sft",
        config_sha="d" * 64,
        seed=42,
        base_model="Qwen/Qwen3.5-2B",
        base_revision="<verify>",
        max_length=2048,
        splits={"train": entry},
        rows_sha256=digest,
    )
    path = tmp_path / "run" / "data_manifest.json"
    sha = write_data_manifest(path, manifest)
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()
    assert DataManifest.model_validate_json(path.read_text(encoding="utf-8")) == manifest
    summary = split_summary(data.val)
    assert summary["records"] == 4
    assert sum(summary["intents"].values()) == 4
    assert [item.record_id for item in gold_items(data.val)] == list(data.val.record_ids)
