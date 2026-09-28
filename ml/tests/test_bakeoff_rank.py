"""E3 bake-off ranking: the §9.5 score, the size rule and incomplete runs."""

import json
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.labelrules import load_label_rules
from tw_ml.datagen.taxonomy import load_taxonomy
from tw_ml.eval import bakeoff
from tw_ml.eval.bakeoff_config import ScoreSettings, load_bakeoff_config
from tw_ml.eval.bakeoff_rank import (
    BakeoffRanking,
    RankedCandidate,
    RankInputs,
    apply_size_rule,
    assess,
    output_agreement,
    score_value,
)
from tw_ml.eval.data import PredictionRecord
from tw_ml.eval.metrics import EvalSettings

SETTINGS = ScoreSettings(
    w_macro_f1=0.40,
    w_min_critical_recall=0.25,
    w_latency=0.20,
    w_license=0.15,
    latency_target_s=5.0,
    min_gain_macro_f1=0.03,
    m08_p50_s=5.0,
    m08_p95_s=12.0,
)
RANKING = "evals/reports/2026-09-27/bakeoff_ranking.json"


def _ranking(env: Any) -> BakeoffRanking:
    path = env.paths.root / RANKING
    return BakeoffRanking.model_validate_json(path.read_text(encoding="utf-8"))


def _run_both_modes(env: Any, *candidates: str) -> None:
    for candidate in candidates:
        assert env.run("--candidate", candidate) == 0
        assert env.run("--candidate", candidate, "--mode", "cpu-sample", "--n", "4") == 0


def test_score_follows_the_spec_formula() -> None:
    score = score_value(SETTINGS, macro_f1=0.8, min_critical_recall=0.9, latency_term=0.5, lic=1.0)
    assert score == pytest.approx(0.795)
    capped = score_value(SETTINGS, macro_f1=0.8, min_critical_recall=0.9, latency_term=3.0, lic=0.5)
    assert capped == pytest.approx(0.32 + 0.225 + 0.20 + 0.075)


def test_rank_scores_complete_runs_and_applies_the_size_rule(
    bakeoff_env: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    wrong = {**env.gold["va_00006"], "intent": "how_to_question"}
    env.ollama.model_answers = {"tw-bakeoff-small-a": {"va_00006": wrong}}
    _run_both_modes(env, "small-a", "big-b")
    capsys.readouterr()
    assert env.rank() == 0
    ranking = _ranking(env)
    assert [r.candidate_id for r in ranking.ranked] == ["big-b", "small-a"]
    big, small = ranking.ranked
    assert big.macro_f1 is not None
    assert small.macro_f1 is not None
    assert big.macro_f1 - small.macro_f1 == pytest.approx(1 / 12)
    assert (big.min_critical_recall, small.min_critical_recall) == (1.0, 1.0)
    assert big.latency_term == small.latency_term == 1.0
    assert big.m08_ok is True
    assert big.score == pytest.approx(0.40 * big.macro_f1 + 0.25 + 0.20 + 0.15)
    assert small.cpu_output_agreement == 1.0
    assert big.n_scored == 6
    assert ranking.top2_for_probe == ("big-b", "small-a")
    assert ranking.provisional_winner == "big-b"
    assert "keeps the lead over the smaller small-a" in ranking.size_rule[0]
    assert ranking.decision_grade is True
    assert [(r.candidate_id, r.status) for r in ranking.not_ranked] == [("tiny-c", "incomplete")]
    assert ranking.not_ranked[0].reasons == ("no val accuracy run",)
    printed = json.loads(capsys.readouterr().out)
    assert printed["provisional_winner"] == "big-b"


def test_incomplete_runs_are_listed_and_never_scored(bakeoff_env: Any) -> None:
    env = bakeoff_env
    assert env.run("--candidate", "small-a") == 0  # no CPU sample
    _run_both_modes(env, "big-b")
    predictions = env.runs_dir / "big-b_val.jsonl"
    predictions.write_text(predictions.read_text("utf-8") + "\n", encoding="utf-8")
    env.ollama.answers = {record_id: ("status", 503) for record_id in env.gold}
    assert env.run("--candidate", "tiny-c") == bakeoff.EXIT_ABORTED
    assert env.rank() == 0
    ranking = _ranking(env)
    assert ranking.ranked == ()
    assert ranking.provisional_winner is None
    assert ranking.decision_grade is False
    reasons = {r.candidate_id: r.reasons for r in ranking.not_ranked}
    assert reasons["small-a"] == ("no CPU sample (run --mode cpu-sample)",)
    assert reasons["big-b"] == ("val accuracy run predictions changed after the run",)
    assert reasons["tiny-c"][0].startswith("val accuracy run aborted (5 consecutive")
    assert all(r.score is None for r in ranking.not_ranked)


def test_missing_predictions_and_non_cpu_latency_are_reasons(bakeoff_env: Any) -> None:
    env = bakeoff_env
    _run_both_modes(env, "small-a", "big-b")
    (env.runs_dir / "small-a_val.jsonl").unlink()
    cpu_summary = env.runs_dir / "big-b_val.cpu.summary.json"
    document = json.loads(cpu_summary.read_text("utf-8"))
    document["latency"]["hardware"] = "default"
    cpu_summary.write_text(json.dumps(document), encoding="utf-8")
    assert env.rank() == 0
    reasons = {r.candidate_id: r.reasons for r in _ranking(env).not_ranked}
    assert reasons["small-a"] == ("val accuracy run predictions are missing",)
    assert reasons["big-b"] == ("the CPU sample has no CPU latency",)


def test_a_zero_license_term_is_excluded(bakeoff_env: Any) -> None:
    env = bakeoff_env
    config, _ = load_bakeoff_config(env.config_path)
    blocked = config.candidate("small-a").model_copy(update={"lic": 0.0})
    taxonomy = load_taxonomy(env.paths.schemas_dir)
    rules = load_label_rules(env.paths.spec_dir / "label_rules.v1.yaml", taxonomy)
    inputs = RankInputs(config, (), env.runs_dir, taxonomy, rules, EvalSettings(n_resamples=10))
    row = assess(blocked, inputs)
    assert (row.status, row.reasons, row.score) == ("excluded", ("non-commercial license",), None)


def test_undefined_critical_recall_keeps_a_candidate_unranked(bakeoff_env: Any) -> None:
    env = bakeoff_env
    _run_both_modes(env, "small-a")
    rows = env.val_path.read_text("utf-8").splitlines()
    subset = env.paths.root / "val_subset.jsonl"
    subset.write_text("".join(row + "\n" for row in rows[1:]), encoding="utf-8")
    out = env.paths.root / "ranking.json"
    assert env.rank("--gold", str(subset), "--out", str(out)) == 0
    ranking = BakeoffRanking.model_validate_json(out.read_text("utf-8"))
    small = next(r for r in ranking.not_ranked if r.candidate_id == "small-a")
    assert small.critical_recall["security_report"] is None
    assert small.reasons == ("a critical class has no val items (min critical recall undefined)",)


def test_unverified_runs_are_not_decision_grade(bakeoff_env: Any) -> None:
    env = bakeoff_env
    env.update_candidates(ollama_digest=None)
    for candidate in ("small-a", "big-b"):
        assert env.run("--candidate", candidate, "--allow-unverified") == 0
        mode = ("--mode", "cpu-sample", "--n", "2", "--allow-unverified")
        assert env.run("--candidate", candidate, *mode) == 0
    assert env.rank() == 0
    ranking = _ranking(env)
    assert len(ranking.ranked) == 2
    assert all(not r.verified for r in ranking.ranked)
    assert ranking.decision_grade is False
    assert any("not decision-grade" in note for note in ranking.notes)


def test_rank_refuses_sealed_gold_and_bad_arguments(
    bakeoff_env: Any, make_record: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    sealed = make_record(
        record_id="ts_00001",
        split="test_synth",
        generator_family="deepseek",
        generator_model="deepseek-ai/DeepSeek-V3.2",
        prompt_family="P-B",
    )
    gold = env.paths.root / "sealed_gold.jsonl"
    gold.write_text(sealed.model_dump_json() + "\n", encoding="utf-8")
    assert env.rank("--gold", str(gold)) == bakeoff.EXIT_USAGE
    assert "refusing to evaluate sealed data" in capsys.readouterr().err
    assert env.rank("--date", "27/09/2026") == bakeoff.EXIT_USAGE
    assert "--date must be YYYY-MM-DD" in capsys.readouterr().err
    document = env.config()
    document["splits"].pop("val")
    env.write_config(document)
    assert env.rank() == bakeoff.EXIT_USAGE
    assert "no val gold configured" in capsys.readouterr().err
    assert not (env.paths.root / RANKING).exists()


def _row(candidate_id: str, size: str, macro: float, *, m08: bool | None = True) -> RankedCandidate:
    return RankedCandidate(
        candidate_id=candidate_id,
        role="test",
        optional=False,
        hf_repo=f"org/{candidate_id}",
        params_b=4.0 if size == "3_4b" else 1.7,
        size_class=size,
        license="apache-2.0",
        lic=1.0,
        macro_f1=macro,
        m08_ok=m08,
        status="ranked",
    )


@pytest.mark.parametrize(
    ("leader", "expected", "fragment"),
    [
        (_row("big", "3_4b", 0.82), "small", "gain +0.020 is below 0.03"),
        (_row("big", "3_4b", 0.83), "big", "keeps the lead"),
        (_row("big", "3_4b", 0.90, m08=False), "small", "M-08 is not met"),
        (_row("big", "3_4b", 0.90, m08=None), "small", "M-08 is not met"),
    ],
)
def test_a_larger_model_needs_three_points_and_m08(
    leader: RankedCandidate, expected: str, fragment: str
) -> None:
    winner, reasoning = apply_size_rule([leader, _row("small", "le_2b", 0.80)], SETTINGS)
    assert winner == expected
    assert fragment in reasoning[0]


def test_size_rule_edges() -> None:
    assert apply_size_rule([], SETTINGS) == (None, ["no candidate is complete: nothing to choose"])
    winner, reasoning = apply_size_rule(
        [_row("small", "le_2b", 0.8), _row("big", "3_4b", 0.9)], SETTINGS
    )
    assert winner == "small"
    assert "no smaller class ranks" in reasoning[0]


def test_output_agreement() -> None:
    def record(record_id: str) -> PredictionRecord:
        return PredictionRecord(record_id=record_id, system_id="s", validity="failed_fallback")

    assert output_agreement([record("a"), record("b")], [record("a"), record("c")]) == 1.0
    assert output_agreement([record("a")], [record("b")]) is None


def test_ranking_file_is_valid_json(bakeoff_env: Any, tmp_path: Path) -> None:
    env = bakeoff_env
    _run_both_modes(env, "small-a")
    out = tmp_path / "r.json"
    assert env.rank("--out", str(out), "--runs-dir", str(env.runs_dir)) == 0
    document = json.loads(out.read_text("utf-8"))
    assert document["schema_version"] == "bakeoff_ranking.v1"
    assert document["weights"] == {
        "macro_f1": 0.4,
        "min_critical_recall": 0.25,
        "latency": 0.2,
        "license": 0.15,
    }
    assert document["gold_file"] == "data/generated/val/records.jsonl"
