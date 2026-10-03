"""Leakage checks C1-C7: true and false positives, policy (never drop test data), gate, report."""

import json
import sys
import types
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from tw_ml.datagen.leakage import (
    EmbeddingConfig,
    LeakageConfig,
    LeakageError,
    LeakageInputs,
    LeakItem,
    LshConfig,
    ShingleIndex,
    apply_drops,
    check_lsh_params,
    decide,
    exact_jaccard,
    file_sha256,
    item_from_row,
    kb_texts,
    load_embedder,
    load_items,
    load_leakage_config,
    lsh_candidates,
    prompt_echo,
    prompt_source_text,
    read_protected_strings,
    run_leakage,
    structural_overlap,
)
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import DatasetRecord
from tw_ml.datagen.text import char_shingles, jaccard

NOW_ISO = "2026-09-27T12:00:00+00:00"
BASE = (
    "The timeline export leaves out every task that has a dependency "
    "and the weekly report is wrong."
)
NEAR = (
    "The timeline export leaves out each task that has a dependency and the weekly report is wrong."
)
OTHER = (
    "Our automation rule sends every notification twice to the whole marketing team since Monday."
)


@pytest.fixture(scope="module")
def cfg(paths: RepoPaths) -> LeakageConfig:
    return load_leakage_config(paths.configs_dir / "leakage.yaml")


def _item(record_id: str, split: str, text: str, **extra: Any) -> LeakItem:
    return LeakItem(record_id=record_id, split=split, text=text, **extra)


def _run(cfg: LeakageConfig, items: Sequence[LeakItem], **inputs: Any) -> Any:
    from datetime import datetime  # noqa: PLC0415

    return run_leakage(
        LeakageInputs(items=items, **inputs), cfg, now=datetime.fromisoformat(NOW_ISO)
    )


def _checks(report: Any) -> set[tuple[str, str, str]]:
    return {(f.check, f.a, f.action) for f in report.flags}


# --------------------------------------------------------------------------- kernels


def test_exact_jaccard_equals_brute_force() -> None:
    rng = np.random.default_rng(7)
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
    texts = [" ".join(rng.choice(words, size=int(rng.integers(3, 12)))) for _ in range(40)]
    index = ShingleIndex(texts, 5)
    scan = exact_jaccard(index, list(range(20)), list(range(20, 40)), 0.0)
    got = {(i, j): score for i, j, score in scan.pairs}
    for i in range(20):
        for j in range(20, 40):
            expected = jaccard(char_shingles(texts[i]), char_shingles(texts[j]))
            if expected > 0:
                assert got[(i, j)] == pytest.approx(expected)
        assert scan.row_max[i] == pytest.approx(
            max(jaccard(char_shingles(texts[i]), char_shingles(texts[j])) for j in range(20, 40))
        )


def test_exact_jaccard_within_one_set_keeps_each_pair_once() -> None:
    index = ShingleIndex([BASE, NEAR, OTHER], 5)
    scan = exact_jaccard(index, [0, 1, 2], [0, 1, 2], 0.7, same=True)
    assert [(i, j) for i, j, _ in scan.pairs] == [(0, 1)]
    assert exact_jaccard(index, [], [1], 0.1).pairs == []


def test_lsh_parameters_are_asserted(cfg: LeakageConfig) -> None:
    assert check_lsh_params(cfg.lsh) == (30, 4)
    wrong = cfg.lsh.model_copy(update={"expected_b": 14, "expected_r": 9})
    with pytest.raises(LeakageError, match="datasketch"):
        check_lsh_params(wrong)


def test_lsh_finds_the_planted_near_duplicate(cfg: LeakageConfig) -> None:
    left = [char_shingles(BASE), char_shingles(OTHER)]
    right = [char_shingles(NEAR)]
    candidates = lsh_candidates(left, right, cfg.lsh)
    assert (0, 0) in candidates
    assert jaccard(left[0], right[0]) >= 0.7


# --------------------------------------------------------------------------- C1 / C2 / C7


def test_c1_exact_duplicates_drop_the_trainable_record(cfg: LeakageConfig) -> None:
    items = [
        _item("tr_00001", "train", BASE),
        _item("ts_00001", "test_synth", BASE.upper().replace("dependency", "Dependency")),
    ]
    report = _run(cfg, items)
    assert ("C1", "tr_00001", "drop_a") in _checks(report)
    assert report.drops == ["tr_00001"]
    assert not report.gate["passed"]


def test_c2_near_duplicates_and_report_band(cfg: LeakageConfig) -> None:
    band = (  # J=0.56
        "The timeline export skips each task that has a dependency "
        "and the weekly report is incorrect."
    )
    items = [
        _item("tr_00001", "train", BASE),
        _item("va_00001", "val", OTHER),
        _item("ts_00001", "test_synth", NEAR),
        _item("ts_00002", "test_synth", OTHER.replace("Monday", "Tuesday and Wednesday")),
        _item("th_001", "test_hard", band),
    ]
    report = _run(cfg, items)
    checks = _checks(report)
    assert ("C2", "tr_00001", "drop_a") in checks  # train x test_synth near-duplicate
    assert ("C2", "va_00001", "drop_a") in checks  # val is trainable too
    assert all(f.split_a in {"train", "val"} for f in report.flags if f.action == "drop_a")
    assert report.report_only["C2_band_pairs"] >= 1
    assert "test_synth->train" in report.nn_similarity_quantiles
    assert report.lsh["b"] == 30
    assert report.lsh["lsh_missed"] == 0


def test_c2_true_negative(cfg: LeakageConfig) -> None:
    report = _run(cfg, [_item("tr_00001", "train", BASE), _item("ts_00001", "test_synth", OTHER)])
    assert report.flags == []
    assert report.gate == {"passed": True, "failures": []}
    assert report.lsh["crosscheck"].startswith("no exact")


def test_c7_within_train_quality_check(cfg: LeakageConfig) -> None:
    items = [
        _item("tr_00002", "train", NEAR),
        _item("tr_00001", "train", BASE),
        _item("tr_00003", "train", OTHER),
    ]
    report = _run(cfg, items)
    assert ("C7", "tr_00001", "drop_b") in _checks(report)  # keep the first id, drop the later
    assert report.drops == ["tr_00002"]
    assert report.gate["passed"]  # quality flags do not fail the leakage gate


# --------------------------------------------------------------------------- C3 embeddings


def _first_word_embedder(texts: Sequence[str]) -> NDArray[np.float32]:
    vocabulary = sorted({t.split()[0].lower() for t in texts})
    vectors = np.zeros((len(texts), len(vocabulary)), dtype=np.float32)
    for row, text in enumerate(texts):
        vectors[row, vocabulary.index(text.split()[0].lower())] = 1.0
    return vectors


def test_c3_embedding_flags_with_an_injected_embedder(cfg: LeakageConfig) -> None:
    items = [
        _item("tr_00001", "train", "Invoices were duplicated after the renewal."),
        _item("ts_00001", "test_synth", "Invoices show up two times since we renewed our seats."),
        _item("ts_00002", "test_synth", "Nothing loads in the EU region."),
    ]
    report = run_leakage(
        LeakageInputs(items=items),
        cfg,
        embedder=_first_word_embedder,
        embedding_status={"status": "ran"},
        now=__import__("datetime").datetime.fromisoformat(NOW_ISO),
    )
    assert ("C3", "tr_00001", "drop_a") in _checks(report)
    assert not any(f.check == "C3" and f.b == "ts_00002" for f in report.flags)
    assert report.embedding == {"status": "ran"}
    assert "test_synth->train(cos)" in report.nn_similarity_quantiles


def test_load_embedder_skips_cleanly(cfg: LeakageConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    disabled, status = load_embedder(cfg.embedding.model_copy(update={"enabled": False}))
    assert disabled is None
    assert status["reason"] == "disabled in config"
    unpinned, status = load_embedder(cfg.embedding.model_copy(update={"revision": None}))
    assert unpinned is None
    assert status["reason"] == "model revision not pinned"
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    missing, status = load_embedder(cfg.embedding.model_copy(update={"revision": "a" * 40}))
    assert missing is None
    assert status["reason"] == "sentence-transformers not installed"


def test_load_embedder_with_a_fake_library(
    cfg: LeakageConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeModel:
        def __init__(self, model_id: str, revision: str, device: str) -> None:
            self.args = (model_id, revision, device)

        def encode(self, texts: list[str], batch_size: int) -> list[list[float]]:
            del batch_size
            return [[3.0, 4.0] for _ in texts]

    fake = types.ModuleType("sentence_transformers")
    fake.__dict__["SentenceTransformer"] = FakeModel
    fake.__dict__["__version__"] = "6.1.0"
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    embedder, status = load_embedder(
        EmbeddingConfig.model_validate({**cfg.embedding.model_dump(), "revision": "b" * 40})
    )
    assert embedder is not None
    assert status["status"] == "ran"
    assert status["sentence_transformers"] == "6.1.0"
    vectors = embedder(["one", "two"])
    assert np.allclose(vectors, [[0.6, 0.8], [0.6, 0.8]])


# --------------------------------------------------------------------------- C4 structure


def test_c4_structural_overlap_fails_the_gate(cfg: LeakageConfig) -> None:
    items = [
        _item(
            "tr_00001", "train", BASE, template_id="pa.t1", persona_id="p_tr_0001", scenario_seed=5
        ),
        _item("va_00001", "val", OTHER, template_id="pa.t1", scenario_seed=5),
        _item(
            "ts_00001",
            "test_synth",
            "Invoice INV-A123456 is wrong.",
            template_id="pb.s1+pb.m1",
            persona_id="p_tr_0001",
        ),
        _item("tr_00002", "train", "Invoice INV-A654321 is odd.", company_id="c_tr_0001"),
        _item("th_001", "test_hard", "Something else entirely here.", company_id="c_tr_0001"),
    ]
    overlap = structural_overlap(items)
    assert overlap["persona_id"] == {"train~test_synth": ["p_tr_0001"]}
    assert overlap["company_id"] == {"train~test_hard": ["c_tr_0001"]}
    assert overlap["template_id"] == {"train~val": ["pa.t1"]}
    assert overlap["scenario_seed"] == {"train~val": ["5"]}
    assert overlap["invoice_prefix"] == {"train~test_synth": ["INV-A"]}
    report = _run(cfg, items)
    assert "C4 structural overlap" in report.gate["failures"]


def test_c4_clean_splits() -> None:
    items = [
        _item("tr_00001", "train", "INV-A123456", template_id="pa.t1", persona_id="p_tr_1"),
        _item(
            "ts_00001", "test_synth", "INV-T123456", template_id="pb.s1+pb.m1", persona_id="p_te_1"
        ),
    ]
    assert all(value == {} for value in structural_overlap(items).values())


# --------------------------------------------------------------------------- C5 KB copying


def test_c5_kb_windows(cfg: LeakageConfig) -> None:
    kb_words = [f"word{i:02d}".replace("0", "o") for i in range(45)]
    kb_words = [w.replace("1", "l").replace("2", "z").replace("3", "e") for w in kb_words]
    document = " ".join(kb_words)
    copied = " ".join(kb_words[:31])
    partial = " ".join(kb_words[:14]) + " and then something unrelated happened to us"
    items = [
        _item("ts_00001", "test_synth", f"Hello. {copied} Thanks."),
        _item("tr_00001", "train", f"Question: {copied}"),
        _item("tr_00002", "train", partial),
        _item("tr_00003", "train", OTHER),
    ]
    report = _run(cfg, items, kb={"help/doc.md": document})
    checks = _checks(report)
    assert ("C5", "ts_00001", "replace_a") in checks  # protected: replace before freeze
    assert ("C5", "tr_00001", "drop_a") in checks
    assert not any(f.check == "C5" and f.a in {"tr_00002", "tr_00003"} for f in report.flags)
    assert [r["record_id"] for r in report.report_only["C5_long_runs"]] == ["tr_00002"]
    assert report.kb["status"] == "ok"
    assert "C5 KB copying in a protected split" in report.gate["failures"]


def test_c5_accepts_an_empty_kb(cfg: LeakageConfig, tmp_path: Path) -> None:
    report = _run(cfg, [_item("tr_00001", "train", BASE)], kb=kb_texts(tmp_path / "kb"))
    assert report.kb == {"documents": 0, "windows": 0, "status": "no_kb_documents"}


def test_kb_texts_strip_front_matter_and_links(tmp_path: Path) -> None:
    (tmp_path / "help").mkdir()
    (tmp_path / "help" / "a.md").write_text(
        "---\ndoc_key: kb_a\n---\nSee [the guide](https://x.test) now.\n", encoding="utf-8"
    )
    assert kb_texts(tmp_path) == {"help/a.md": "See the guide now.\n"}


# --------------------------------------------------------------------------- C6 protected strings


def test_c6_protected_strings_in_every_split(cfg: LeakageConfig, paths: RepoPaths) -> None:
    entries = read_protected_strings(paths.spec_dir / "protected_strings.txt")
    guideline = "We will not renew when the contract ends in May."
    assert guideline in entries
    items = [
        _item("tr_00001", "train", f"Hi. {guideline} Also the export is slow."),  # containment
        _item("ts_00001", "test_synth", "We were billed $1,280 twice this month"),  # Jaccard
        _item(
            "th_001",
            "test_hard",
            "Honestly, the timeline view keeps crashing, "
            "can I speak to a human about it? It is urgent.",
        ),  # 8-word span
        _item("tr_00002", "train", OTHER),
    ]
    report = _run(cfg, items, protected_strings=entries)
    c6 = {(f.a, f.action) for f in report.flags if f.check == "C6"}
    assert ("tr_00001", "drop_a") in c6
    assert ("ts_00001", "replace_a") in c6
    assert ("th_001", "replace_a") in c6
    assert not any(a == "tr_00002" for a, _ in c6)
    assert report.report_only["C6_entries"] == len(entries)
    assert not report.gate["passed"]


def test_read_protected_strings_skips_comments(tmp_path: Path) -> None:
    path = tmp_path / "p.txt"
    path.write_text("# comment\n\nfirst entry\n  second entry  \n", encoding="utf-8")
    assert read_protected_strings(path) == ["first entry", "second entry"]


# --------------------------------------------------------------------------- policy and gate


@pytest.mark.parametrize(
    ("a", "b", "target", "kind"),
    [
        (("tr_1", "train"), ("ts_1", "test_synth"), "tr_1", "drop"),
        (("ts_1", "test_synth"), ("tr_1", "train"), "tr_1", "drop"),  # argument order is irrelevant
        (("va_1", "val"), ("tr_1", "train"), "tr_1", "drop"),  # train x val drops the train record
        (("tr_9", "train"), ("tr_2", "train"), "tr_9", "drop"),  # within a split: keep the first id
        (("ts_1", "test_synth"), ("th_001", "test_hard"), "ts_1", "replace"),  # keep the human one
        (("ts_9", "test_synth"), ("ts_2", "test_synth"), "ts_9", "replace"),
    ],
)
def test_policy_never_drops_protected_records(
    a: tuple[str, str], b: tuple[str, str], target: str, kind: str
) -> None:
    flag = decide("C2", _item(a[0], a[1], "x"), _item(b[0], b[1], "y"), 0.9)
    acted_on = flag.a if flag.action.endswith("_a") else flag.b
    acted_split = flag.split_a if flag.action.endswith("_a") else flag.split_b
    assert acted_on == target
    assert flag.action.split("_")[0] == kind
    if kind == "drop":
        assert acted_split in {"train", "val"}


def test_protected_duplicates_are_replaced_not_dropped(cfg: LeakageConfig) -> None:
    items = [
        _item("ts_00001", "test_synth", BASE),
        _item("ts_00002", "test_synth", BASE),
        _item("th_001", "test_hard", NEAR),
    ]
    report = _run(cfg, items)
    assert report.drops == []
    replaced = {r["old_id"] for r in report.replacements}
    assert replaced == {"ts_00002", "ts_00001"}
    assert any("replace before freeze" in f for f in report.gate["failures"])


def test_report_format(cfg: LeakageConfig) -> None:
    report = _run(cfg, [_item("tr_00001", "train", BASE), _item("ts_00001", "test_synth", NEAR)])
    payload = json.loads(report.to_json())
    assert payload["report_version"] == "leakage.v1"
    for key in (
        "created_at",
        "config",
        "inputs",
        "counts",
        "flags",
        "drops",
        "replacements",
        "disjointness",
        "kb",
        "embedding",
        "lsh",
        "nn_similarity_quantiles",
        "prompt_echo",
        "gate",
    ):
        assert key in payload, key
    assert payload["config"]["normalization"] == "nfkc|placeholders|lower|digits0|ws"
    assert payload["config"]["lsh"]["weights"] == [0.2, 0.8]
    assert payload["counts"]["train~test_synth"]["C2"] == 1
    assert payload["inputs"] == {"test_synth": 1, "train": 1}


def test_prompt_echo_probe(cfg: LeakageConfig, paths: RepoPaths) -> None:
    source = prompt_source_text(paths.prompts_dir / "pa_persona.v1.txt")
    assert "{{" not in source
    echo = (
        "Write in the customer's own voice, not as an assistant. "
        "Output one JSON object and nothing else."
    )
    items = [
        _item("tr_00001", "train", echo, intent="bug_report"),
        _item("tr_00002", "train", OTHER, intent="bug_report"),
    ]
    result = prompt_echo(items, {"pa": source}, cfg.prompt_echo)
    assert result["records_with_echo"] == 1
    assert result["intent_rates"] == {"bug_report": 0.5}
    assert result["intents_over_limit"] == ["bug_report"]


# --------------------------------------------------------------------------- IO helpers


def test_items_from_records_and_files(
    make_record: Callable[..., DatasetRecord],
    write_jsonl: Callable[[Path, list[Any]], Path],
    tmp_path: Path,
) -> None:
    record = make_record()
    row = json.loads(record.model_dump_json())
    item = item_from_row(row)
    assert (item.record_id, item.split, item.intent, item.template_id) == (
        "tr_00001",
        "train",
        "sso_login_failure",
        "pa.t1",
    )
    path = write_jsonl(tmp_path / "train.jsonl", [row, ""])
    assert load_items(path) == [item]
    assert len(file_sha256(path)) == 64
    assert apply_drops([row], ["tr_00001"]) == []
    assert apply_drops([row], ["tr_00002"]) == [row]


def test_config_errors(tmp_path: Path) -> None:
    bad = tmp_path / "leakage.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(LeakageError, match="malformed"):
        load_leakage_config(bad)
    assert LshConfig.model_fields["weights"].annotation is not None
