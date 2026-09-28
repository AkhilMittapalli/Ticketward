"""tw_ml.eval.report and tw_ml.eval.gates: schema round trip, rendering, provenance, gates."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from tw_ml.datagen.labelrules import load_label_rules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import TriageLabels
from tw_ml.datagen.taxonomy import load_taxonomy
from tw_ml.eval import report as rpt
from tw_ml.eval.data import GoldItem, PredictionRecord, join
from tw_ml.eval.gates import GATES, Gate, evaluate_gates
from tw_ml.eval.metrics import EvalSettings, evaluate
from tw_ml.eval.stats import Interval

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
RUN_ID = UUID("12345678-1234-5678-1234-567812345678")
SECRET = "Confidential ticket text 4471"


@pytest.fixture
def sample_report(make_labels: Callable[..., TriageLabels]) -> rpt.EvalReport:
    taxonomy = load_taxonomy()
    rules = load_label_rules(taxonomy=taxonomy)
    gold = [
        GoldItem("va_1", make_labels(rationale=SECRET)),
        GoldItem("va_2", make_labels(intent="bug_report")),
    ]
    predictions = [PredictionRecord(record_id="va_1", system_id="sys-a", output=make_labels())]
    eval_set = join(gold, predictions)
    settings = EvalSettings(n_resamples=200, seed=3)
    suite = evaluate(eval_set, taxonomy, rules, settings)
    return rpt.build_report(
        suite=suite,
        experiment="E1",
        split="val",
        system=rpt.SystemInfo(system_id="sys-a"),
        provenance=rpt.RunProvenance(
            git_sha="a" * 40,
            gold_file="val.jsonl",
            gold_sha256="b" * 64,
            prediction_files={"sys-a": "c" * 64},
            data_manifests={"data/manifests/val.json": "d" * 64},
            analysis_plan_file="evals/ANALYSIS_PLAN.md",
            analysis_plan_sha="e" * 64,
            taxonomy_version=taxonomy.version,
            label_rules_version=rules.version,
            tool_versions=rpt.tool_versions(),
        ),
        holdout=rpt.HoldoutInfo(split="val", sealed=False, phase="P2", origins={"val": 2}),
        counts=rpt.Counts(
            n_gold=2, n_predictions=1, n_scored=2, n_missing=1, n_extra=0, n_with_decision=0
        ),
        settings=settings,
        created_at=NOW,
        run_id=RUN_ID,
        notes=("extra note",),
    )


def test_report_schema_round_trip(sample_report: rpt.EvalReport, tmp_path: Path) -> None:
    assert sample_report.schema_version == "eval_report.v1"
    path = rpt.write_model(tmp_path / "r.json", sample_report)
    assert rpt.load_report(path) == sample_report
    assert rpt.EvalReport.model_validate_json(sample_report.model_dump_json()) == sample_report
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["run_id"] == str(RUN_ID)
    assert raw["bootstrap"] == {"n_resamples": 200, "rng_seed": 3, "level": 0.95}
    assert "extra note" in raw["notes"]
    macro = sample_report.metric("M-01.intent_macro_f1")
    assert macro is not None
    assert macro.n == 2
    assert sample_report.metric("nope") is None
    assert {"intent", "critical_model"} <= set(sample_report.per_class)
    assert sample_report.gates == ()  # no gate applies to E1 on val
    with pytest.raises(ValidationError):
        rpt.EvalReport.model_validate({**raw, "schema_version": "eval_report.v0"})
    with pytest.raises(ValidationError):
        rpt.EvalReport.model_validate({**raw, "unexpected": 1})


def test_report_json_never_contains_ticket_text(sample_report: rpt.EvalReport) -> None:
    assert SECRET not in sample_report.model_dump_json()
    assert SECRET not in rpt.render_report(sample_report)


def test_confusion_matrix_shape_is_validated() -> None:
    with pytest.raises(ValidationError, match="gold_labels x predicted_labels"):
        rpt.ConfusionMatrix(gold_labels=("a", "b"), predicted_labels=("a",), counts=((1,),))


def test_render_report_sections(sample_report: rpt.EvalReport) -> None:
    text = rpt.render_report(sample_report)
    assert text.startswith("# E1 on val: sys-a\n")
    for section in (
        "## Metrics",
        "## Per class: intent",
        "## Confusion matrix: intent",
        "## Validity tiers",
        "## Notes",
    ):
        assert section in text
    assert "| M-01.intent_accuracy | 0.500 [" in text
    assert "B = 200, seed 3" in text
    assert "evals/ANALYSIS_PLAN.md (eeeeeeeeeeee)" in text
    assert "inv" in text  # the invalid column of the confusion matrix
    combined = rpt.render_index([sample_report, sample_report], title="P2 baselines")
    assert combined.startswith("# P2 baselines\n")
    assert combined.count("## E1 on val: sys-a") == 2
    assert "| M-01.intent_macro_f1 |" in combined


def test_seed_aggregate_and_formatting() -> None:
    aggregate = rpt.seed_aggregate(
        "M-01.intent_macro_f1",
        {"42": 0.80, "1337": 0.82, "2026": None},
        level=0.95,
        seed_mean=Interval(0.81, 0.78, 0.84, "two-level", 10),
        deployed_seed="1337",
    )
    assert aggregate.n_seeds == 3
    assert aggregate.mean == pytest.approx(0.81)
    assert aggregate.deployed_seed == "1337"
    assert aggregate.seed_mean_ci is not None
    assert aggregate.seed_mean_ci.low == 0.78
    empty = rpt.seed_aggregate("m", {"42": None}, level=0.95)
    assert empty.mean is None
    assert rpt.fmt(None) == "n/a"
    assert rpt.fmt_estimate(rpt.estimate_model("m", Interval(0.5, None, None, "x", 1))) == "0.500"
    assert rpt.slug("tw-triage-qwen35-2b-lora@0.1.0+abc") == "tw-triage-qwen35-2b-lora-0.1.0-abc"
    assert rpt.report_basename("E4", "val", "A B") == "E4_val_a-b"


# --------------------------------------------------------------------------- provenance

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_git_sha_from_loose_packed_detached_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    assert rpt.git_sha(tmp_path) is None
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert rpt.git_sha(tmp_path) is None  # branch without commits
    (git / "packed-refs").write_text(f"# pack-refs\n{SHA} refs/heads/main\n", encoding="utf-8")
    assert rpt.git_sha(tmp_path) == SHA
    (git / "refs" / "heads" / "main").write_text(SHA.replace("0", "f") + "\n", encoding="utf-8")
    assert rpt.git_sha(tmp_path) == SHA.replace("0", "f")
    (git / "HEAD").write_text(SHA + "\n", encoding="utf-8")  # detached
    assert rpt.git_sha(tmp_path) == SHA
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    assert rpt.git_sha(tmp_path) == "b" * 40


def test_git_sha_in_a_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    common = tmp_path / "main.git"
    worktree = common / "worktrees" / "wt"
    worktree.mkdir(parents=True)
    (worktree / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    (worktree / "commondir").write_text("../..\n", encoding="utf-8")
    (common / "refs" / "heads").mkdir(parents=True)
    (common / "refs" / "heads" / "feature").write_text(SHA + "\n", encoding="utf-8")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text(f"gitdir: {worktree.as_posix()}\n", encoding="utf-8")
    assert rpt.git_sha(checkout) == SHA
    (checkout / ".git").write_text("garbage\n", encoding="utf-8")
    assert rpt.git_sha(checkout) is None


def test_hashes_are_line_ending_independent(tmp_path: Path) -> None:
    paths = RepoPaths(tmp_path)
    assert rpt.analysis_plan_sha(paths) is None
    plan = paths.analysis_plan_file
    plan.parent.mkdir(parents=True)
    plan.write_bytes(b"# Plan\nline\n")
    lf = rpt.analysis_plan_sha(paths)
    plan.write_bytes(b"# Plan\r\nline\r\n")
    assert rpt.analysis_plan_sha(paths) == lf
    manifest = paths.manifests_dir / "test_hard.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    hashes = rpt.manifest_hashes(paths, ["hard_dev", "val"])
    assert list(hashes) == ["data/manifests/test_hard.json"]
    assert rpt.display_path(tmp_path.parent / "elsewhere.json", tmp_path) == "elsewhere.json"


def test_render_comparison() -> None:
    delta = rpt.estimate_model("delta.intent_macro_f1", Interval(0.12, 0.05, 0.19, "paired", 90))
    row = rpt.ComparisonRow(
        hypothesis="H1",
        system_a="e4",
        system_b="e3",
        alternative="greater",
        macro_f1_a=0.8,
        macro_f1_b=0.68,
        delta_macro_f1=delta,
        delta_accuracy=delta,
        p_randomization=0.001,
        mcnemar=rpt.McNemarSummary(n10=20, n01=4, p_exact=0.002, p_midp=0.001),
        p_holm=0.003,
        reject_holm=True,
        acceptance="E4 - E3 >= +0.10: met",
    )
    provenance = rpt.RunProvenance(
        git_sha=None,
        gold_file="g.jsonl",
        gold_sha256="b" * 64,
        prediction_files={},
        data_manifests={},
        analysis_plan_file=None,
        analysis_plan_sha=None,
        taxonomy_version="2026-09-v1",
        label_rules_version="label_rules.v1",
        tool_versions={},
    )
    report = rpt.ComparisonReport(
        run_id=RUN_ID,
        created_at=NOW,
        split="val",
        family="confirmatory",
        alpha=0.05,
        provenance=provenance,
        holdout=rpt.HoldoutInfo(split="val", sealed=False, phase="P2", origins={"val": 90}),
        bootstrap=rpt.BootstrapSettings(n_resamples=100, rng_seed=1, level=0.95),
        n_items=90,
        comparisons=(row,),
        notes=("n",),
    )
    text = rpt.render_comparison(report)
    assert "confirmatory family" in text
    assert "| H1 | e4 vs e3 | greater | 0.120 [0.050, 0.190]" in text
    assert "0.0030 (reject)" in text
    assert rpt.ComparisonReport.model_validate_json(report.model_dump_json()) == report


# --------------------------------------------------------------------------- gates


def test_gates_apply_to_their_split_and_experiment() -> None:
    estimates = {
        "M-07a.forced_escalation": Interval(1.0, 0.95, 1.0, "clopper-pearson", 60, 60),
        "M-03c.system.pooled_recall": Interval(0.94, 0.92, 0.96, "wilson", 600, 564),
        "M-07c.over_escalation": Interval(0.10, 0.08, 0.13, "wilson", 400, 40),
    }
    outcomes = {o.gate.gate_id: o for o in evaluate_gates(estimates, "test_synth", "E5")}
    assert outcomes["G-M07a"].passed is True
    assert outcomes["G-M03c-pooled-test"].passed is False
    assert outcomes["G-M03c-pooled-test"].ci_covers_threshold is True  # inconclusive miss
    assert outcomes["G-M07c"].passed is True
    assert outcomes["G-M02-test"].passed is None  # metric not computed: undefined, not a pass
    assert evaluate_gates(estimates, "val", "E1") == []
    assert {o.gate.gate_id for o in evaluate_gates(estimates, "hard_dev", "E5")} == {"G-M07a"}
    miss = evaluate_gates(
        {"M-07a.forced_escalation": Interval(0.98, 0.9, 1.0, "wilson", 50, 49)}, "smoke", "E5"
    )
    assert miss[0].passed is False


def test_gate_comparators() -> None:
    at_least = Gate("g", "m", ">=", 0.9, frozenset({"s"}), frozenset({"E4"}), "x")
    at_most = Gate("g", "m", "<=", 0.15, frozenset({"s"}), frozenset({"E4"}), "x")
    exactly = Gate("g", "m", "==", 1.0, frozenset({"s"}), frozenset({"E4"}), "x")
    assert at_least.holds(0.9)
    assert not at_least.holds(0.8999)
    assert at_most.holds(0.15)
    assert not at_most.holds(0.16)
    assert exactly.holds(1.0)
    assert not exactly.holds(0.999)
    assert at_least.applies("s", "E4")
    assert not at_least.applies("s", "E5")
    assert len({g.gate_id for g in GATES}) == len(GATES)
