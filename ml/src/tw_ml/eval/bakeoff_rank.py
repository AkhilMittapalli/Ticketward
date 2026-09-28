"""Ranking of the E3 bake-off (spec v1.1 §9.5 "Score" and "Decision rule"; A-02).

``python -m tw_ml.eval.bakeoff rank`` reads, for every candidate of the config:

* the complete val accuracy run (``<id>_val.jsonl`` and its summary), scored against the val
  gold with :func:`tw_ml.eval.metrics.evaluate`: intent macro-F1 (M-01) and the model-level
  recall of each critical class (M-03c), whose minimum enters the score;
* the complete CPU sample (``<id>_val.cpu.summary.json``): triage wall-time P50/P95 and M-08;
* the license term Lic of the config.

``S = 0.40 macroF1 + 0.25 min_critical_recall + 0.20 min(1, 5 s / triage_P50) + 0.15 Lic``
(weights from ``bakeoff.yaml``). A candidate without both runs is listed as incomplete and is
never scored with a guessed term; Lic = 0 (non-commercial) is excluded. The size rule follows:
a candidate of the larger size class (§9.5 method table: <= 2B vs 3-4B) keeps the lead over the
best smaller one only with a macro-F1 gain of at least 3 points **and** M-08 met on its CPU
sample; otherwise the smaller one becomes the provisional winner. The top 2 by S go to the
1-epoch fine-tune probe, and the final choice (ADR-0011) applies the §9.5 decision rule to the
probe results. The gold must be val: the holdout guard refuses anything else.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from tw_ml.datagen.labelrules import LabelRules, load_label_rules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy
from tw_ml.eval.bakeoff import (
    BakeoffError,
    CandidateSummary,
    RunFiles,
    config_path,
    run_tag,
)
from tw_ml.eval.bakeoff_config import (
    SIZE_RANK,
    BakeoffConfig,
    Candidate,
    ScoreSettings,
    load_bakeoff_config,
)
from tw_ml.eval.data import (
    GoldItem,
    PredictionRecord,
    file_sha256,
    join,
    load_gold,
    load_predictions,
)
from tw_ml.eval.holdout import authorize, load_subsets
from tw_ml.eval.metrics import EvalSettings, critical_intents, evaluate
from tw_ml.eval.report import display_path, write_model

RANKING_VERSION: Final = "bakeoff_ranking.v1"
LABEL_RULES_FILE: Final = "label_rules.v1.yaml"
EXIT_OK: Final = 0
Status = Literal["ranked", "incomplete", "excluded"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RankedCandidate(_Model):
    """One candidate's score terms, score and status."""

    candidate_id: str
    role: str
    optional: bool
    hf_repo: str
    params_b: float
    size_class: str
    license: str
    lic: float
    system_id: str | None = None
    verified: bool = False
    n_scored: int = 0
    macro_f1: float | None = None
    macro_f1_ci: tuple[float | None, float | None] | None = None
    critical_recall: dict[str, float | None] = Field(default_factory=dict)
    min_critical_recall: float | None = None
    json_validity: float | None = None
    triage_p50_s: float | None = None
    triage_p95_s: float | None = None
    latency_term: float | None = None
    m08_ok: bool | None = None
    cpu_output_agreement: float | None = None
    score: float | None = None
    status: Status
    reasons: tuple[str, ...] = ()


class BakeoffRanking(_Model):
    """``bakeoff_ranking.v1``: the §9.5 score table and the size rule."""

    schema_version: Literal["bakeoff_ranking.v1"] = RANKING_VERSION
    created_at: AwareDatetime
    config_version: str
    config_sha256: str
    split: Literal["val"] = "val"
    gold_file: str
    gold_sha256: str
    weights: dict[str, float]
    min_gain_macro_f1: float
    ranked: tuple[RankedCandidate, ...]
    not_ranked: tuple[RankedCandidate, ...]
    top2_for_probe: tuple[str, ...]
    provisional_winner: str | None
    size_rule: tuple[str, ...]
    decision_grade: bool
    notes: tuple[str, ...] = ()


def score_value(
    settings: ScoreSettings,
    *,
    macro_f1: float,
    min_critical_recall: float,
    latency_term: float,
    lic: float,
) -> float:
    """The §9.5 bake-off score.

    Args:
        settings: Weights.
        macro_f1: Intent macro-F1 on val.
        min_critical_recall: Lowest model-level recall of the five critical classes on val.
        latency_term: ``min(1, target / triage P50)`` from the CPU sample.
        lic: License term.

    Returns:
        ``S`` in ``[0, 1]``, rounded to 6 decimals.
    """
    total = (
        settings.w_macro_f1 * macro_f1
        + settings.w_min_critical_recall * min_critical_recall
        + settings.w_latency * min(1.0, latency_term)
        + settings.w_license * lic
    )
    return round(total, 6)


def read_summary(path: Path) -> CandidateSummary | None:
    """Read a run summary.

    Args:
        path: ``<tag>.summary.json``.

    Returns:
        The summary, or ``None`` when absent or unreadable.
    """
    try:
        return CandidateSummary.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValidationError):
        return None


def output_agreement(
    reference: Sequence[PredictionRecord], other: Sequence[PredictionRecord]
) -> float | None:
    """Share of shared records with the same validity and output (the CPU spot check).

    Args:
        reference: Accuracy-run predictions.
        other: CPU-sample predictions.

    Returns:
        The agreement, or ``None`` without shared records.
    """
    by_id = {record.record_id: record for record in reference}
    shared = [(by_id[r.record_id], r) for r in other if r.record_id in by_id]
    if not shared:
        return None
    same = sum(a.validity == b.validity and a.output == b.output for a, b in shared)
    return round(same / len(shared), 6)


def _run_problem(summary: CandidateSummary | None, files: RunFiles, what: str) -> str | None:
    if summary is None:
        return f"no {what}"
    if summary.status != "complete":
        return f"{what} aborted ({summary.abort_reason})"
    if summary.smoke_limit is not None:  # pragma: no cover - smoke runs have their own files
        return f"{what} is a smoke run"
    if not files.predictions.is_file():
        return f"{what} predictions are missing"
    if file_sha256(files.predictions) != summary.files.get("predictions_sha256"):
        return f"{what} predictions changed after the run"
    return None


@dataclass(frozen=True, slots=True)
class RankInputs:
    """What every assessment shares."""

    config: BakeoffConfig
    gold: tuple[GoldItem, ...]
    runs_dir: Path
    taxonomy: Taxonomy
    rules: LabelRules
    settings: EvalSettings


def assess(candidate: Candidate, inputs: RankInputs) -> RankedCandidate:
    """Score terms of one candidate from its runs.

    Args:
        candidate: Candidate.
        inputs: Shared inputs.

    Returns:
        The candidate's row (``ranked``, ``incomplete`` or ``excluded``).
    """
    blank = RankedCandidate(
        candidate_id=candidate.id,
        role=candidate.role,
        optional=candidate.optional,
        hf_repo=candidate.hf_repo,
        params_b=candidate.params_b,
        size_class=candidate.size_class,
        license=candidate.license,
        lic=candidate.lic,
        status="incomplete",
    )
    if candidate.lic <= 0:
        return blank.model_copy(
            update={"status": "excluded", "reasons": ("non-commercial license",)}
        )
    files = RunFiles.for_tag(inputs.runs_dir, run_tag(candidate.id, "val", "accuracy", smoke=False))
    summary = read_summary(files.summary)
    problem = _run_problem(summary, files, "val accuracy run")
    if problem is not None or summary is None:
        return blank.model_copy(update={"reasons": (problem or "no run",)})
    predictions = load_predictions(files.predictions)
    suite = evaluate(join(inputs.gold, predictions), inputs.taxonomy, inputs.rules, inputs.settings)
    macro = suite.metrics.get("M-01.intent_macro_f1")
    recalls = {
        intent: suite.point(f"M-03c.model.{intent}_recall")
        for intent in critical_intents(inputs.taxonomy, inputs.rules)
    }
    defined = [value for value in recalls.values() if value is not None]
    reasons: list[str] = []
    if len(defined) != len(recalls):
        reasons.append("a critical class has no val items (min critical recall undefined)")
    cpu_files = RunFiles.for_tag(
        inputs.runs_dir, run_tag(candidate.id, "val", "cpu_sample", smoke=False)
    )
    cpu = read_summary(cpu_files.summary)
    cpu_problem = _run_problem(cpu, cpu_files, "CPU sample (run --mode cpu-sample)")
    latency = cpu.latency if cpu is not None and cpu_problem is None else None
    if cpu_problem is not None:
        reasons.append(cpu_problem)
    elif latency is None or latency.hardware != "cpu" or latency.latency_term is None:
        reasons.append("the CPU sample has no CPU latency")
        latency = None
    agreement = (
        output_agreement(predictions, load_predictions(cpu_files.predictions))
        if cpu is not None and cpu_problem is None
        else None
    )
    row = blank.model_copy(
        update={
            "system_id": summary.system_id,
            "verified": summary.verified and cpu is not None and cpu.verified,
            "n_scored": suite.n_items,
            "macro_f1": macro.estimate.point if macro is not None else None,
            "macro_f1_ci": (macro.estimate.low, macro.estimate.high) if macro is not None else None,
            "critical_recall": recalls,
            "min_critical_recall": min(defined) if len(defined) == len(recalls) else None,
            "json_validity": suite.point("M-04.json_validity"),
            "triage_p50_s": latency.triage_p50_s if latency is not None else None,
            "triage_p95_s": latency.triage_p95_s if latency is not None else None,
            "latency_term": latency.latency_term if latency is not None else None,
            "m08_ok": (
                bool(latency.m08_p50_ok and latency.m08_p95_ok)
                if latency is not None and latency.m08_p50_ok is not None
                else None
            ),
            "cpu_output_agreement": agreement,
            "reasons": tuple(reasons),
        }
    )
    if reasons:
        return row  # never scored with a missing or guessed term
    if row.macro_f1 is None or row.min_critical_recall is None or row.latency_term is None:
        return row.model_copy(update={"reasons": ("score terms undefined",)})  # pragma: no cover
    score = score_value(
        inputs.config.score,
        macro_f1=row.macro_f1,
        min_critical_recall=row.min_critical_recall,
        latency_term=row.latency_term,
        lic=candidate.lic,
    )
    return row.model_copy(update={"score": score, "status": "ranked"})


def apply_size_rule(
    ranked: Sequence[RankedCandidate], settings: ScoreSettings
) -> tuple[str | None, list[str]]:
    """The provisional winner after the "larger model wins only with >= 3 points" rule.

    Args:
        ranked: Ranked candidates, best S first.
        settings: Score settings (minimum gain).

    Returns:
        The winner id (``None`` without ranked candidates) and the reasoning lines.
    """
    if not ranked:
        return None, ["no candidate is complete: nothing to choose"]
    leader = ranked[0]
    smaller = [r for r in ranked if SIZE_RANK[r.size_class] < SIZE_RANK[leader.size_class]]
    if not smaller:
        return leader.candidate_id, [f"{leader.candidate_id} leads by S; no smaller class ranks"]
    best = smaller[0]
    gain = (leader.macro_f1 or 0.0) - (best.macro_f1 or 0.0)
    enough = gain >= settings.min_gain_macro_f1 - 1e-9
    if enough and leader.m08_ok is True:
        line = (
            f"{leader.candidate_id} ({leader.size_class}) keeps the lead over the smaller "
            f"{best.candidate_id}: macro-F1 gain {gain:+.3f} with M-08 met"
        )
        return leader.candidate_id, [line]
    why = (
        f"macro-F1 gain {gain:+.3f} is below {settings.min_gain_macro_f1:.2f}"
        if not enough
        else "M-08 is not met on its CPU sample"
    )
    line = (
        f"{leader.candidate_id} ({leader.size_class}) yields to the smaller "
        f"{best.candidate_id}: {why}"
    )
    return best.candidate_id, [line]


def rank_bakeoff(
    config: BakeoffConfig,
    config_sha256: str,
    *,
    gold_path: Path,
    runs_dir: Path,
    paths: RepoPaths,
    now: datetime,
    n_resamples: int,
    phase: str,
) -> BakeoffRanking:
    """Score every candidate's complete val runs and apply the size rule.

    Args:
        config: Bake-off config.
        config_sha256: Its hash.
        gold_path: Val gold file.
        runs_dir: Folder with the run files.
        paths: Repository paths.
        now: Clock.
        n_resamples: Bootstrap B for the macro-F1 interval.
        phase: Current project phase.

    Returns:
        The ranking.
    """
    gold = load_gold(gold_path)
    authorize(
        "val",
        [(item.record_id, item.origin) for item in gold],
        phase=phase,
        i_understand_sealed=False,
        subsets=load_subsets(paths),
    )
    taxonomy = load_taxonomy(paths.schemas_dir)
    rules = load_label_rules(paths.spec_dir / LABEL_RULES_FILE, taxonomy)
    inputs = RankInputs(
        config, tuple(gold), runs_dir, taxonomy, rules, EvalSettings(n_resamples=n_resamples)
    )
    rows = [assess(candidate, inputs) for candidate in config.candidates]
    ranked = sorted(
        (row for row in rows if row.status == "ranked"),
        key=lambda r: (-(r.score or 0.0), SIZE_RANK[r.size_class], r.params_b, r.candidate_id),
    )
    winner, reasoning = apply_size_rule(ranked, config.score)
    decision_grade = bool(ranked) and all(row.verified for row in ranked)
    notes = ["zero-shot only: ADR-0011 applies the §9.5 decision rule to the 1-epoch probe"]
    if not decision_grade:
        notes.append("not decision-grade: unverified runs or no complete candidate")
    score = config.score
    return BakeoffRanking(
        created_at=now,
        config_version=config.version,
        config_sha256=config_sha256,
        gold_file=display_path(gold_path, paths.root),
        gold_sha256=file_sha256(gold_path),
        weights={
            "macro_f1": score.w_macro_f1,
            "min_critical_recall": score.w_min_critical_recall,
            "latency": score.w_latency,
            "license": score.w_license,
        },
        min_gain_macro_f1=score.min_gain_macro_f1,
        ranked=tuple(ranked),
        not_ranked=tuple(row for row in rows if row.status != "ranked"),
        top2_for_probe=tuple(row.candidate_id for row in ranked[:2]),
        provisional_winner=winner,
        size_rule=tuple(reasoning),
        decision_grade=decision_grade,
        notes=tuple(notes),
    )


def cmd_rank(args: argparse.Namespace, paths: RepoPaths, now: datetime) -> int:
    """``rank``: write ``evals/reports/<date>/bakeoff_ranking.json``.

    Args:
        args: Parsed arguments.
        paths: Repository paths.
        now: Clock.

    Returns:
        Exit code 0 (errors raise and become exit code 2 in ``main``).

    Raises:
        BakeoffError: If the date is malformed or no val gold is configured.
    """
    path = config_path(args, paths)
    config, config_sha256 = load_bakeoff_config(path)
    if args.gold is None and "val" not in config.splits:
        msg = "no val gold configured; pass --gold"
        raise BakeoffError(msg)
    gold = Path(args.gold) if args.gold else paths.root / config.splits["val"]
    try:
        day = date.fromisoformat(args.date).isoformat() if args.date else now.date().isoformat()
    except ValueError:
        msg = "--date must be YYYY-MM-DD"
        raise BakeoffError(msg) from None
    ranking = rank_bakeoff(
        config,
        config_sha256,
        gold_path=gold,
        runs_dir=Path(args.runs_dir) if args.runs_dir else paths.root / config.output_dir,
        paths=paths,
        now=now,
        n_resamples=args.n_resamples,
        phase=args.phase,
    )
    out = write_model(
        Path(args.out) if args.out else paths.reports_dir / day / "bakeoff_ranking.json", ranking
    )
    brief = {
        "ranking": out.as_posix(),
        "ranked": [{"id": r.candidate_id, "score": r.score} for r in ranking.ranked],
        "top2_for_probe": list(ranking.top2_for_probe),
        "provisional_winner": ranking.provisional_winner,
        "decision_grade": ranking.decision_grade,
        "not_ranked": [
            {"id": r.candidate_id, "reasons": list(r.reasons)} for r in ranking.not_ranked
        ],
    }
    sys.stdout.write(json.dumps(brief, indent=2) + "\n")
    return EXIT_OK
