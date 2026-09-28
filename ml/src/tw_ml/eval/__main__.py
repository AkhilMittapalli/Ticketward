"""``python -m tw_ml.eval <command>``: score, compare and render evaluation reports.

Commands::

    score    --pred P [--pred LABEL=P ...] --gold G --split S --experiment E1
             [--deployed-seed LABEL] [--system-id ID] [--out-dir D] [--date YYYY-MM-DD]
             [--n-resamples 10000] [--seed 2026] [--phase P2] [--i-understand-sealed]
             [--fail-on-gate]
    compare  --gold G --split S --pred-a A --pred-b B [--pred-b B ...]
             [--family confirmatory | --alternative two-sided|greater] [--alpha 0.05] ...
    render   --report R.json [--report R2.json ...] [--out OUT.md] [--title T]

Every ``score`` and ``compare`` run passes the holdout guard first (``tw_ml.eval.holdout``):
sealed splits are refused unless ``--phase P10 --i-understand-sealed`` is given, and each sealed
evaluation is appended to ``evals/sealed_access.jsonl``. Several ``--pred`` files are seeds of one
system (E2/E4): the report shows the deployed seed's metrics plus every seed's value, the mean,
the SD with its chi-square CI and the two-level bootstrap CI of the seed-mean macro-F1.

Exit codes: 0 success, 1 an applicable gate failed (with ``--fail-on-gate``), 2 usage, data or
holdout error.
"""

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, get_args
from uuid import uuid4

from tw_ml.datagen.labelrules import LabelRules, load_label_rules
from tw_ml.datagen.paths import RepoPaths, default_paths
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy
from tw_ml.eval import report as rpt
from tw_ml.eval.data import (
    EvalDataError,
    EvalSet,
    GoldItem,
    PredictionRecord,
    file_sha256,
    join,
    load_gold,
    load_predictions,
)
from tw_ml.eval.gates import E4_MINUS_E3_MIN
from tw_ml.eval.holdout import (
    ALLOWED_ORIGINS,
    AccessDecision,
    HoldoutError,
    SealedAccess,
    authorize,
    load_subsets,
    log_sealed_access,
)
from tw_ml.eval.metrics import (
    SEED_METRICS,
    EvalSettings,
    MetricSuite,
    compare_systems,
    evaluate,
    seed_mean_macro_f1,
)
from tw_ml.eval.stats import B_DEFAULT, RNG_SEED, Alternative, holm

EXIT_OK: Final = 0
EXIT_GATE: Final = 1
EXIT_USAGE: Final = 2
LABEL_RULES_FILE: Final = "label_rules.v1.yaml"
CONFIRMATORY: Final[tuple[tuple[str, str, Alternative], ...]] = (
    ("H1", "E3", "greater"),
    ("H2", "E1", "greater"),
    ("H3", "E2", "two-sided"),
)
"""Pre-registered family (ANALYSIS_PLAN §6): E4 against E3, E1 and E2, in this order."""
_PHASE: Final = re.compile(r"^P(?:[0-9]|1[01])$")
_LABEL: Final = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


class UsageError(ValueError):
    """Raised for inconsistent command-line arguments."""


@dataclass(frozen=True, slots=True)
class Context:
    """Shared inputs of every command.

    Attributes:
        paths: Repository paths.
        taxonomy: Taxonomy.
        rules: Label rules.
        now: Wall clock (injected by tests).
    """

    paths: RepoPaths
    taxonomy: Taxonomy
    rules: LabelRules
    now: datetime


def _write(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _labelled(values: Sequence[str]) -> list[tuple[str, Path]]:
    """Parse ``PATH`` or ``LABEL=PATH`` arguments (labels name seeds)."""
    pairs: list[tuple[str, Path]] = []
    for value in values:
        label, sep, rest = value.partition("=")
        if sep and _LABEL.fullmatch(label):
            pairs.append((label, Path(rest)))
        else:
            pairs.append((Path(value).stem, Path(value)))
    labels = [label for label, _ in pairs]
    if len(set(labels)) != len(labels):
        msg = "prediction labels must be unique (use LABEL=PATH)"
        raise UsageError(msg)
    return pairs


def _system_id(records: Sequence[PredictionRecord], override: str | None) -> str:
    if override:
        return override
    ids = sorted({record.system_id for record in records})
    if len(ids) != 1:
        msg = f"prediction file has {len(ids)} system ids; pass --system-id"
        raise UsageError(msg)
    return ids[0]


def _authorize(args: argparse.Namespace, ctx: Context, gold: Sequence[GoldItem]) -> AccessDecision:
    return authorize(
        args.split,
        [(item.record_id, item.origin) for item in gold],
        phase=args.phase,
        i_understand_sealed=args.i_understand_sealed,
        subsets=load_subsets(ctx.paths),
    )


def _log_if_sealed(
    decision: AccessDecision,
    ctx: Context,
    *,
    action: str,
    system_id: str,
    experiment: str | None,
    gold_file: Path,
    prediction_files: Sequence[Path],
    n_records: int,
) -> int | None:
    if not decision.sealed:
        return None
    return log_sealed_access(
        ctx.paths.sealed_access_log,
        SealedAccess(
            at=ctx.now,
            action=action,
            split=decision.split or "(records)",
            system_id=system_id,
            experiment=experiment,
            phase=decision.phase,
            gold_sha256=file_sha256(gold_file),
            predictions_sha256=tuple(file_sha256(p) for p in prediction_files),
            git_sha=rpt.git_sha(ctx.paths.root),
            n_records=n_records,
        ),
    )


def _provenance(
    ctx: Context, gold_file: Path, predictions: Sequence[tuple[str, Path]], decision: AccessDecision
) -> rpt.RunProvenance:
    plan = ctx.paths.analysis_plan_file
    return rpt.RunProvenance(
        git_sha=rpt.git_sha(ctx.paths.root),
        gold_file=gold_file.name,
        gold_sha256=file_sha256(gold_file),
        prediction_files={label: file_sha256(path) for label, path in predictions},
        data_manifests=rpt.manifest_hashes(ctx.paths, decision.origins),
        analysis_plan_file=rpt.display_path(plan, ctx.paths.root) if plan.is_file() else None,
        analysis_plan_sha=rpt.analysis_plan_sha(ctx.paths),
        taxonomy_version=ctx.taxonomy.version,
        label_rules_version=ctx.rules.version,
        tool_versions=rpt.tool_versions(),
    )


def _holdout(decision: AccessDecision, split: str, count: int | None) -> rpt.HoldoutInfo:
    return rpt.HoldoutInfo(
        split=split,
        sealed=decision.sealed,
        phase=decision.phase,
        origins=dict(decision.origins),
        eval_count_on_split=count,
        notes=decision.notes,
    )


def _out_dir(args: argparse.Namespace, ctx: Context) -> Path:
    if args.out_dir:
        return Path(args.out_dir)
    day = args.date or ctx.now.date().isoformat()
    return ctx.paths.reports_dir / day


def _seed_aggregates(
    suites: dict[str, MetricSuite],
    sets: dict[str, EvalSet],
    ctx: Context,
    settings: EvalSettings,
    deployed: str,
) -> list[rpt.SeedAggregate]:
    seed_mean = seed_mean_macro_f1(list(sets.values()), ctx.taxonomy, settings)
    return [
        rpt.seed_aggregate(
            metric_id,
            {label: suite.point(metric_id) for label, suite in suites.items()},
            level=settings.level,
            seed_mean=seed_mean if metric_id == "M-01.intent_macro_f1" else None,
            deployed_seed=deployed,
        )
        for metric_id in SEED_METRICS
    ]


def cmd_score(args: argparse.Namespace, ctx: Context) -> int:
    """Score one system (one or several seeds) on one split and write the report."""
    gold_file = Path(args.gold)
    gold = load_gold(gold_file)
    predictions = _labelled(args.pred)
    loaded = {label: load_predictions(path) for label, path in predictions}
    if len(loaded) > 1 and args.deployed_seed not in loaded:
        msg = "several --pred files are seeds: --deployed-seed must name one of their labels"
        raise UsageError(msg)
    deployed = args.deployed_seed or next(iter(loaded))
    decision = _authorize(args, ctx, gold)
    system_id = _system_id(loaded[deployed], args.system_id)
    count = _log_if_sealed(
        decision,
        ctx,
        action="score",
        system_id=system_id,
        experiment=args.experiment,
        gold_file=gold_file,
        prediction_files=[path for _, path in predictions],
        n_records=len(gold),
    )
    settings = EvalSettings(n_resamples=args.n_resamples, seed=args.seed)
    sets = {label: join(gold, records) for label, records in loaded.items()}
    suites = {label: evaluate(s, ctx.taxonomy, ctx.rules, settings) for label, s in sets.items()}
    main_set, suite = sets[deployed], suites[deployed]
    seeds = _seed_aggregates(suites, sets, ctx, settings, deployed) if len(sets) > 1 else []
    report = rpt.build_report(
        suite=suite,
        experiment=args.experiment,
        split=args.split,
        system=rpt.SystemInfo(
            system_id=system_id,
            seeds=tuple(loaded) if len(loaded) > 1 else (),
            deployed_seed=deployed if len(loaded) > 1 else None,
        ),
        provenance=_provenance(ctx, gold_file, predictions, decision),
        holdout=_holdout(decision, args.split, count),
        counts=rpt.Counts(
            n_gold=len(gold),
            n_predictions=len(loaded[deployed]),
            n_scored=len(main_set.items),
            n_missing=len(main_set.missing),
            n_extra=len(main_set.extra),
            n_with_decision=main_set.n_with_decision,
        ),
        settings=settings,
        created_at=ctx.now,
        seeds=seeds,
    )
    folder = _out_dir(args, ctx)
    base = rpt.report_basename(args.experiment, args.split, system_id)
    if count is not None and count > 1:
        base += f"_run{count}"  # a repeated sealed evaluation never overwrites the first report
    json_path = rpt.write_model(folder / f"{base}.json", report)
    md_path = rpt.write_text(folder / f"{base}.md", rpt.render_report(report))
    failed = [g.gate_id for g in report.gates if g.passed is False]
    headline = {m: report.metric(m) for m in ("M-01.intent_macro_f1", "M-04.json_validity")}
    _write(
        json.dumps(
            {
                "report": json_path.as_posix(),
                "markdown": md_path.as_posix(),
                "system_id": system_id,
                "split": args.split,
                "sealed": decision.sealed,
                "eval_count_on_split": count,
                "headline": {k: v.point if v else None for k, v in headline.items()},
                "gates_failed": failed,
            },
            indent=2,
        )
    )
    return EXIT_GATE if failed and args.fail_on_gate else EXIT_OK


def cmd_compare(args: argparse.Namespace, ctx: Context) -> int:
    """Paired comparison of system A against one or more systems B (Holm over the family)."""
    gold_file = Path(args.gold)
    gold = load_gold(gold_file)
    predictions = _labelled([args.pred_a, *args.pred_b])
    loaded = {label: load_predictions(path) for label, path in predictions}
    labels = list(loaded)
    if args.family == "confirmatory" and len(labels) != 1 + len(CONFIRMATORY):
        msg = "--family confirmatory needs --pred-a E4 and --pred-b E3, E1, E2 in this order"
        raise UsageError(msg)
    decision = _authorize(args, ctx, gold)
    system_a = _system_id(loaded[labels[0]], None)
    _log_if_sealed(
        decision,
        ctx,
        action="compare",
        system_id=system_a,
        experiment=None,
        gold_file=gold_file,
        prediction_files=[path for _, path in predictions],
        n_records=len(gold),
    )
    settings = EvalSettings(n_resamples=args.n_resamples, seed=args.seed)
    set_a = join(gold, loaded[labels[0]])
    alternative: Alternative = "greater" if args.alternative == "greater" else "two-sided"
    plan: list[tuple[str | None, str | None, Alternative]] = (
        list(CONFIRMATORY)
        if args.family == "confirmatory"
        else [(None, None, alternative) for _ in labels[1:]]
    )
    results = [
        compare_systems(set_a, join(gold, loaded[label]), ctx.taxonomy, settings, alternative=alt)
        for label, (_, _, alt) in zip(labels[1:], plan, strict=True)
    ]
    adjusted, reject = holm([r.p_randomization for r in results], alpha=args.alpha)
    rows = []
    for (hypothesis, baseline, _), result, p_holm, rejected in zip(
        plan, results, adjusted, reject, strict=True
    ):
        acceptance = None
        if hypothesis == "H1" and result.delta_macro_f1.point is not None:
            met = result.delta_macro_f1.point >= E4_MINUS_E3_MIN
            superior = rejected and (result.delta_macro_f1.low or 0.0) > 0
            acceptance = (
                f"E4 - E3 >= +{E4_MINUS_E3_MIN:.2f}: {'met' if met else 'NOT met'}; "
                f"superiority {'shown' if superior else 'not shown'}"
            )
        elif hypothesis is not None:
            acceptance = f"vs {baseline}: {'reject H0' if rejected else 'retain H0'} (Holm)"
        rows.append(
            rpt.ComparisonRow(
                hypothesis=hypothesis,
                system_a=result.system_a,
                system_b=result.system_b,
                alternative=result.alternative,
                macro_f1_a=result.macro_f1_a,
                macro_f1_b=result.macro_f1_b,
                delta_macro_f1=rpt.estimate_model("delta.intent_macro_f1", result.delta_macro_f1),
                delta_accuracy=rpt.estimate_model("delta.intent_accuracy", result.delta_accuracy),
                p_randomization=result.p_randomization,
                mcnemar=rpt.McNemarSummary(
                    n10=result.mcnemar.n10,
                    n01=result.mcnemar.n01,
                    p_exact=result.mcnemar.p_exact,
                    p_midp=result.mcnemar.p_midp,
                ),
                p_holm=p_holm,
                reject_holm=rejected,
                acceptance=acceptance,
            )
        )
    notes = (
        ()
        if args.family == "confirmatory"
        else ("exploratory comparisons are descriptive; adjusted p-values are for orientation",)
    )
    report = rpt.ComparisonReport(
        run_id=uuid4(),
        created_at=ctx.now,
        split=args.split,
        family=args.family,
        alpha=args.alpha,
        provenance=_provenance(ctx, gold_file, predictions, decision),
        holdout=_holdout(decision, args.split, None),
        bootstrap=rpt.BootstrapSettings(
            n_resamples=settings.n_resamples, rng_seed=settings.seed, level=settings.level
        ),
        n_items=len(set_a.items),
        comparisons=tuple(rows),
        notes=notes,
    )
    folder = _out_dir(args, ctx)
    base = f"compare_{args.split}_{rpt.slug(system_a)}"
    json_path = rpt.write_model(folder / f"{base}.json", report)
    md_path = rpt.write_text(folder / f"{base}.md", rpt.render_comparison(report))
    _write(json.dumps({"report": json_path.as_posix(), "markdown": md_path.as_posix()}, indent=2))
    return EXIT_OK


def cmd_render(args: argparse.Namespace, ctx: Context) -> int:
    """Render one report, or combine several into one page."""
    del ctx
    reports = [rpt.load_report(Path(path)) for path in args.report]
    if len(reports) == 1 and not args.title:
        text = rpt.render_report(reports[0])
    else:
        text = rpt.render_index(reports, title=args.title or "Evaluation reports")
    if args.out:
        rpt.write_text(Path(args.out), text)
        _write(f"wrote {Path(args.out).as_posix()}")
    else:
        _write(text)
    return EXIT_OK


# --------------------------------------------------------------------------- parser


def _phase(value: str) -> str:
    if not _PHASE.fullmatch(value):
        msg = "phase must be P0..P11"
        raise argparse.ArgumentTypeError(msg)
    return value


def _day(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        msg = "date must be YYYY-MM-DD"
        raise argparse.ArgumentTypeError(msg) from None


def _positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        msg = "must be a positive integer"
        raise argparse.ArgumentTypeError(msg)
    return number


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gold", required=True, help="gold JSONL (any P1 row format)")
    parser.add_argument("--split", required=True, choices=tuple(ALLOWED_ORIGINS))
    parser.add_argument("--out-dir", help="report folder (default evals/reports/<date>/)")
    parser.add_argument("--date", type=_day, help="report date folder (default today, UTC)")
    parser.add_argument("--n-resamples", type=_positive, default=B_DEFAULT)
    parser.add_argument("--seed", type=int, default=RNG_SEED, help="bootstrap RNG seed")
    parser.add_argument("--phase", type=_phase, default="P2", help="current project phase")
    parser.add_argument(
        "--i-understand-sealed",
        action="store_true",
        help="with --phase P10 only: evaluate a sealed split (logged to evals/sealed_access.jsonl)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tw_ml.eval", description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = parser.add_subparsers(dest="command", required=True)
    score = sub.add_parser("score", help="score one system on one split")
    _common(score)
    score.add_argument("--pred", action="append", required=True, help="PATH or SEED=PATH")
    score.add_argument("--experiment", required=True, choices=get_args(rpt.Experiment))
    score.add_argument("--deployed-seed", help="label of the val-selected seed (multi-seed runs)")
    score.add_argument("--system-id", help="override the predictions' system_id")
    score.add_argument("--fail-on-gate", action="store_true", help="exit 1 when a gate fails")
    compare = sub.add_parser("compare", help="paired tests of system A against systems B")
    _common(compare)
    compare.add_argument("--pred-a", required=True, help="system A predictions")
    compare.add_argument("--pred-b", action="append", required=True, help="system B predictions")
    compare.add_argument("--family", choices=("exploratory", "confirmatory"), default="exploratory")
    compare.add_argument("--alternative", choices=("two-sided", "greater"), default="two-sided")
    compare.add_argument("--alpha", type=float, default=0.05)
    render = sub.add_parser("render", help="render report JSON as Markdown")
    render.add_argument("--report", action="append", required=True, help="eval_report.v1 JSON")
    render.add_argument("--out", help="write here instead of stdout")
    render.add_argument("--title", help="combined page title (baselines.md, bakeoff.md)")
    return parser


COMMANDS: Final = {"score": cmd_score, "compare": cmd_compare, "render": cmd_render}


def main(
    argv: Sequence[str] | None = None,
    paths: RepoPaths | None = None,
    now: datetime | None = None,
) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).
        paths: Repository paths override (tests).
        now: Clock override (tests).

    Returns:
        Process exit code.
    """
    args = build_parser().parse_args(argv)
    paths = paths or default_paths()
    taxonomy = load_taxonomy(paths.schemas_dir)
    ctx = Context(
        paths=paths,
        taxonomy=taxonomy,
        rules=load_label_rules(paths.spec_dir / LABEL_RULES_FILE, taxonomy),
        now=now or datetime.now(UTC),
    )
    try:
        return COMMANDS[args.command](args, ctx)
    except (EvalDataError, HoldoutError, UsageError) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
