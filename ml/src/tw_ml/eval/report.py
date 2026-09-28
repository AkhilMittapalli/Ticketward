"""Versioned evaluation reports (``eval_report.v1``, ``eval_comparison.v1``) and Markdown.

One JSON report per (experiment, split, system) run is written to ``evals/reports/<date>/``
next to its Markdown rendering; ``render`` combines several into ``baselines.md`` or
``bakeoff.md`` (spec §9.9, P2.18). Every report carries what makes it reproducible and
auditable: the git SHA, the gold and prediction file hashes, the data-manifest hashes,
``analysis_plan_sha``, the bootstrap settings, the holdout decision and, for sealed splits,
``eval_count_on_split``. Each metric is one record with point, CI, method, ``n``, ``k``,
resamples and seed (ERPROT evaluation-statistics D9); numbers are published as
``point [low, high]``.
"""

import hashlib
import os
import platform
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, Self
from uuid import UUID, uuid4

import numpy as np
import scipy
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

import tw_ml
from tw_ml.datagen.paths import RepoPaths
from tw_ml.eval.gates import GateOutcome, evaluate_gates
from tw_ml.eval.metrics import ClassStats, Confusion, EvalSettings, MetricSuite
from tw_ml.eval.stats import Interval, seed_summary

REPORT_SCHEMA_VERSION: Final = "eval_report.v1"
COMPARISON_SCHEMA_VERSION: Final = "eval_comparison.v1"
EXPERIMENTS: Final[tuple[str, ...]] = ("E1", "E2", "E3", "E4", "E5", "E6")
Experiment = Literal["E1", "E2", "E3", "E4", "E5", "E6"]
HEADLINE_METRICS: Final[tuple[str, ...]] = (
    "M-01.intent_macro_f1",
    "M-01.intent_accuracy",
    "M-01.other_unclear_f1",
    "M-02.routing_accuracy",
    "M-03.priority_accuracy",
    "M-03.priority_within_one",
    "M-03.sentiment_macro_f1",
    "M-03.churn_macro_f1",
    "M-03.product_area_accuracy",
    "M-03.entity_f1",
    "M-03c.model.pooled_recall",
    "M-03c.system.pooled_recall",
    "M-04.json_validity",
    "M-07a.forced_escalation",
    "M-07d.human_request_recall",
)
"""Rows of the combined summary table (``render``)."""
_SHA: Final = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
_SLUG: Final = re.compile(r"[^a-z0-9._-]+")
_MANIFEST_FOR: Final[Mapping[str, str]] = {"hard_dev": "test_hard", "hard_final": "test_hard"}


class ReportModel(BaseModel):
    """Base of every report model: closed, immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Estimate(ReportModel):
    """One metric of one run: ``point [low, high]`` with method, ``n`` and ``k``."""

    metric: str
    point: float | None
    low: float | None
    high: float | None
    level: float = Field(gt=0, lt=1)
    method: str
    n: int = Field(ge=0)
    k: int | None = Field(default=None, ge=0)
    n_resamples: int | None = Field(default=None, ge=1)
    rng_seed: int | None = None
    lower_bound_one_sided: float | None = None
    notes: str = ""


class ClassRow(ReportModel):
    """Per-class counts and rates."""

    label: str
    support: int = Field(ge=0)
    predicted: int | None = Field(default=None, ge=0)
    tp: int = Field(ge=0)
    precision: float | None
    recall: float | None
    f1: float | None
    recall_low: float | None
    recall_high: float | None
    recall_method: str


class ConfusionMatrix(ReportModel):
    """Rows are gold labels, columns predicted labels."""

    gold_labels: tuple[str, ...]
    predicted_labels: tuple[str, ...]
    counts: tuple[tuple[int, ...], ...]

    @model_validator(mode="after")
    def _shape(self) -> Self:
        width = len(self.predicted_labels)
        if len(self.counts) != len(self.gold_labels) or any(len(r) != width for r in self.counts):
            msg = "confusion counts must be gold_labels x predicted_labels"
            raise ValueError(msg)
        return self


class GateResult(ReportModel):
    """A gate outcome, published with the metric's CI (gates are decisions, not tests)."""

    gate_id: str
    metric: str
    comparator: Literal[">=", "<=", "=="]
    threshold: float
    source: str
    point: float | None
    low: float | None
    high: float | None
    n: int | None
    passed: bool | None
    ci_covers_threshold: bool | None


class SeedAggregate(ReportModel):
    """A metric across seeds: every seed's value, mean, SD with its chi-square CI and range."""

    metric: str
    per_seed: dict[str, float | None]
    mean: float | None
    sd: float | None
    sd_low: float | None
    sd_high: float | None
    minimum: float | None
    maximum: float | None
    n_seeds: int = Field(ge=1)
    seed_mean_ci: Estimate | None = None
    deployed_seed: str | None = None


class SystemInfo(ReportModel):
    """The evaluated system (``tw-triage-<base>-<method>@<semver>``, the rules baseline...)."""

    system_id: str = Field(min_length=1)
    seeds: tuple[str, ...] = ()
    deployed_seed: str | None = None


class RunProvenance(ReportModel):
    """Everything needed to reproduce and audit a run."""

    git_sha: str | None
    gold_file: str
    gold_sha256: str
    prediction_files: dict[str, str]
    data_manifests: dict[str, str]
    analysis_plan_file: str | None
    analysis_plan_sha: str | None
    taxonomy_version: str
    label_rules_version: str
    tool_versions: dict[str, str]


class HoldoutInfo(ReportModel):
    """The holdout guard's decision."""

    split: str
    sealed: bool
    phase: str
    origins: dict[str, int]
    eval_count_on_split: int | None = None
    notes: tuple[str, ...] = ()


class BootstrapSettings(ReportModel):
    """Resampling settings shared by every interval of the report."""

    n_resamples: int = Field(ge=1)
    rng_seed: int
    level: float = Field(gt=0, lt=1)


class Counts(ReportModel):
    """Record counts."""

    n_gold: int = Field(ge=0)
    n_predictions: int = Field(ge=0)
    n_scored: int = Field(ge=0)
    n_missing: int = Field(ge=0)
    n_extra: int = Field(ge=0)
    n_with_decision: int = Field(ge=0)


class EvalReport(ReportModel):
    """One system on one split (``eval_report.v1``)."""

    schema_version: Literal["eval_report.v1"] = REPORT_SCHEMA_VERSION
    run_id: UUID
    created_at: AwareDatetime
    experiment: Experiment
    split: str
    system: SystemInfo
    provenance: RunProvenance
    holdout: HoldoutInfo
    bootstrap: BootstrapSettings
    counts: Counts
    metrics: tuple[Estimate, ...]
    per_class: dict[str, tuple[ClassRow, ...]]
    confusion: dict[str, ConfusionMatrix]
    validity_counts: dict[str, int]
    gates: tuple[GateResult, ...] = ()
    seeds: tuple[SeedAggregate, ...] = ()
    notes: tuple[str, ...] = ()

    def metric(self, metric_id: str) -> Estimate | None:
        """Look a metric up by id.

        Args:
            metric_id: Metric id.

        Returns:
            The estimate, or ``None``.
        """
        return next((m for m in self.metrics if m.metric == metric_id), None)


class McNemarSummary(ReportModel):
    """McNemar on per-ticket intent correctness."""

    n10: int = Field(ge=0)
    n01: int = Field(ge=0)
    p_exact: float = Field(ge=0, le=1)
    p_midp: float = Field(ge=0, le=1)


class ComparisonRow(ReportModel):
    """System A against one system B."""

    hypothesis: str | None = None
    system_a: str
    system_b: str
    alternative: Literal["two-sided", "greater"]
    macro_f1_a: float | None
    macro_f1_b: float | None
    delta_macro_f1: Estimate
    delta_accuracy: Estimate
    p_randomization: float = Field(ge=0, le=1)
    mcnemar: McNemarSummary
    p_holm: float = Field(ge=0, le=1)
    reject_holm: bool
    acceptance: str | None = None


class ComparisonReport(ReportModel):
    """Paired comparisons of one system against a family of others (``eval_comparison.v1``)."""

    schema_version: Literal["eval_comparison.v1"] = COMPARISON_SCHEMA_VERSION
    run_id: UUID
    created_at: AwareDatetime
    split: str
    family: Literal["confirmatory", "exploratory"]
    alpha: float = Field(gt=0, lt=1)
    provenance: RunProvenance
    holdout: HoldoutInfo
    bootstrap: BootstrapSettings
    n_items: int = Field(ge=0)
    comparisons: tuple[ComparisonRow, ...]
    notes: tuple[str, ...] = ()


# --------------------------------------------------------------------------- building


def estimate_model(
    metric_id: str, interval: Interval, *, lower_bound: float | None = None, notes: str = ""
) -> Estimate:
    """Convert a statistics interval into its report record.

    Args:
        metric_id: Metric id.
        interval: Estimate.
        lower_bound: One-sided lower bound, if any.
        notes: Caveats.

    Returns:
        The report record.
    """
    return Estimate(
        metric=metric_id,
        point=interval.point,
        low=interval.low,
        high=interval.high,
        level=interval.level,
        method=interval.method,
        n=interval.n,
        k=interval.k,
        n_resamples=interval.n_resamples,
        rng_seed=interval.rng_seed,
        lower_bound_one_sided=lower_bound,
        notes=notes,
    )


def class_rows(rows: Sequence[ClassStats]) -> tuple[ClassRow, ...]:
    """Convert per-class statistics.

    Args:
        rows: Suite rows.

    Returns:
        Report rows.
    """
    return tuple(
        ClassRow(
            label=r.label,
            support=r.support,
            predicted=r.predicted,
            tp=r.tp,
            precision=r.precision,
            recall=r.recall,
            f1=r.f1,
            recall_low=r.recall_interval.low,
            recall_high=r.recall_interval.high,
            recall_method=r.recall_interval.method,
        )
        for r in rows
    )


def confusion_model(matrix: Confusion) -> ConfusionMatrix:
    """Convert a confusion matrix.

    Args:
        matrix: Suite matrix.

    Returns:
        Report matrix.
    """
    return ConfusionMatrix(
        gold_labels=matrix.gold_labels,
        predicted_labels=matrix.predicted_labels,
        counts=matrix.counts,
    )


def gate_results(outcomes: Iterable[GateOutcome]) -> tuple[GateResult, ...]:
    """Convert gate outcomes.

    Args:
        outcomes: Evaluated gates.

    Returns:
        Report records.
    """
    return tuple(
        GateResult(
            gate_id=o.gate.gate_id,
            metric=o.gate.metric_id,
            comparator=o.gate.comparator,
            threshold=o.gate.threshold,
            source=o.gate.source,
            point=o.estimate.point if o.estimate else None,
            low=o.estimate.low if o.estimate else None,
            high=o.estimate.high if o.estimate else None,
            n=o.estimate.n if o.estimate else None,
            passed=o.passed,
            ci_covers_threshold=o.ci_covers_threshold,
        )
        for o in outcomes
    )


def seed_aggregate(
    metric_id: str,
    per_seed: Mapping[str, float | None],
    *,
    level: float,
    seed_mean: Interval | None = None,
    deployed_seed: str | None = None,
) -> SeedAggregate:
    """Aggregate one metric across seeds (undefined seed values are listed, not averaged).

    Args:
        metric_id: Metric id.
        per_seed: Seed label to value.
        level: Level of the SD interval.
        seed_mean: Two-level bootstrap CI of the seed mean, when computed.
        deployed_seed: The val-selected deployed seed.

    Returns:
        The aggregate.
    """
    defined = {seed: value for seed, value in per_seed.items() if value is not None}
    summary = seed_summary(defined, level=level) if defined else None
    return SeedAggregate(
        metric=metric_id,
        per_seed=dict(per_seed),
        mean=summary.mean if summary else None,
        sd=summary.sd if summary else None,
        sd_low=summary.sd_low if summary else None,
        sd_high=summary.sd_high if summary else None,
        minimum=summary.minimum if summary else None,
        maximum=summary.maximum if summary else None,
        n_seeds=len(per_seed),
        seed_mean_ci=estimate_model(metric_id, seed_mean) if seed_mean else None,
        deployed_seed=deployed_seed,
    )


def build_report(  # noqa: PLR0913 - keyword-only: one argument per report section
    *,
    suite: MetricSuite,
    experiment: Experiment,
    split: str,
    system: SystemInfo,
    provenance: RunProvenance,
    holdout: HoldoutInfo,
    counts: Counts,
    settings: EvalSettings,
    created_at: datetime,
    seeds: Sequence[SeedAggregate] = (),
    run_id: UUID | None = None,
    notes: Sequence[str] = (),
) -> EvalReport:
    """Assemble an ``eval_report.v1`` from a metric suite.

    Args:
        suite: Scored metrics (of the deployed seed for multi-seed runs).
        experiment: Experiment id.
        split: Split.
        system: System info.
        provenance: Reproducibility fields.
        holdout: Guard decision.
        counts: Record counts.
        settings: Bootstrap settings.
        created_at: Creation time (aware).
        seeds: Across-seed aggregates.
        run_id: Run id (random when omitted).
        notes: Extra caveats.

    Returns:
        The report.
    """
    estimates = {mid: value.estimate for mid, value in suite.metrics.items()}
    return EvalReport(
        run_id=run_id or uuid4(),
        created_at=created_at,
        experiment=experiment,
        split=split,
        system=system,
        provenance=provenance,
        holdout=holdout,
        bootstrap=BootstrapSettings(
            n_resamples=settings.n_resamples, rng_seed=settings.seed, level=settings.level
        ),
        counts=counts,
        metrics=tuple(
            estimate_model(
                mid, value.estimate, lower_bound=value.lower_bound_one_sided, notes=value.notes
            )
            for mid, value in suite.metrics.items()
        ),
        per_class={name: class_rows(rows) for name, rows in suite.per_class.items()},
        confusion={name: confusion_model(m) for name, m in suite.confusion.items()},
        validity_counts=dict(suite.validity_counts),
        gates=gate_results(evaluate_gates(estimates, split, experiment)),
        seeds=tuple(seeds),
        notes=(*suite.notes, *notes),
    )


# --------------------------------------------------------------------------- provenance


def text_sha256(path: Path) -> str:
    """SHA-256 of a text file with line endings normalized to LF (checkout-independent).

    Args:
        path: UTF-8 text file.

    Returns:
        Hex digest.
    """
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def display_path(path: Path, root: Path) -> str:
    """Repository-relative POSIX path, or the bare file name for paths outside the repository.

    Args:
        path: Any path.
        root: Repository root.

    Returns:
        A path safe to publish (never an absolute local path).
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def analysis_plan_sha(paths: RepoPaths) -> str | None:
    """``analysis_plan_sha``: the LF-normalized SHA-256 of ``evals/ANALYSIS_PLAN.md``.

    Args:
        paths: Repository paths.

    Returns:
        The digest, or ``None`` when the plan does not exist.
    """
    plan = paths.analysis_plan_file
    return text_sha256(plan) if plan.is_file() else None


def manifest_hashes(paths: RepoPaths, origins: Iterable[str]) -> dict[str, str]:
    """SHA-256 of the committed manifest of every split the gold records come from.

    Args:
        paths: Repository paths.
        origins: Effective record origins (``val``, ``hard_dev``...).

    Returns:
        Repository-relative manifest path to digest (manifests that do not exist are omitted).
    """
    hashes: dict[str, str] = {}
    for origin in sorted(set(origins)):
        manifest = paths.manifests_dir / f"{_MANIFEST_FOR.get(origin, origin)}.json"
        if manifest.is_file():
            relative = display_path(manifest, paths.root)
            hashes[relative] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return hashes


def _read_ref(git_dirs: Sequence[Path], ref: str) -> str | None:
    for directory in git_dirs:
        loose = directory / ref
        if loose.is_file():
            value = loose.read_text(encoding="utf-8").strip()
            return value if _SHA.fullmatch(value) else None
        packed = directory / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                sha, _, name = line.partition(" ")
                if name.strip() == ref and _SHA.fullmatch(sha):
                    return sha
    return None


def git_sha(root: Path) -> str | None:
    """Commit SHA of the checkout, read from ``.git`` without running git.

    ``TW_GIT_SHA`` or ``GITHUB_SHA`` take precedence (CI). Worktrees (``.git`` file with
    ``gitdir:``) and packed refs are supported.

    Args:
        root: Repository root.

    Returns:
        The SHA, or ``None`` when it cannot be determined.
    """
    for variable in ("TW_GIT_SHA", "GITHUB_SHA"):
        value = os.environ.get(variable, "").strip()
        if _SHA.fullmatch(value):
            return value
    git = root / ".git"
    if git.is_file():
        pointer = git.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir:"):
            return None
        git = (root / pointer.removeprefix("gitdir:").strip()).resolve()
    head_file = git / "HEAD"
    if not head_file.is_file():
        return None
    head = head_file.read_text(encoding="utf-8").strip()
    if _SHA.fullmatch(head):
        return head
    if not head.startswith("ref:"):
        return None
    dirs = [git]
    common = git / "commondir"
    if common.is_file():
        dirs.append((git / common.read_text(encoding="utf-8").strip()).resolve())
    return _read_ref(dirs, head.removeprefix("ref:").strip())


def tool_versions() -> dict[str, str]:
    """Versions of the code that produced a report.

    Returns:
        Package name to version.
    """
    return {
        "tw_ml": tw_ml.__version__,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }


# --------------------------------------------------------------------------- files


def slug(text: str) -> str:
    """File-name-safe form of a system id.

    Args:
        text: Any text.

    Returns:
        Lowercase ``[a-z0-9._-]`` slug (at most 80 characters).
    """
    return _SLUG.sub("-", text.lower()).strip("-")[:80] or "system"


def report_basename(experiment: str, split: str, system_id: str) -> str:
    """Base file name of a run's report.

    Args:
        experiment: Experiment id.
        split: Split.
        system_id: System id.

    Returns:
        ``<experiment>_<split>_<system-slug>``.
    """
    return f"{experiment}_{split}_{slug(system_id)}"


def write_model(path: Path, model: BaseModel) -> Path:
    """Write a model as pretty JSON (LF).

    Args:
        path: Destination.
        model: Pydantic model.

    Returns:
        The path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def write_text(path: Path, text: str) -> Path:
    """Write UTF-8 text with LF line endings.

    Args:
        path: Destination.
        text: Content.

    Returns:
        The path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n")
    return path


def load_report(path: Path) -> EvalReport:
    """Read an ``eval_report.v1`` file.

    Args:
        path: JSON report.

    Returns:
        The report.
    """
    return EvalReport.model_validate_json(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- Markdown


def fmt(value: float | None, digits: int = 3) -> str:
    """Format a number for a table.

    Args:
        value: Number or ``None``.
        digits: Decimals.

    Returns:
        The formatted value, or ``n/a``.
    """
    return "n/a" if value is None else f"{value:.{digits}f}"


def fmt_estimate(estimate: Estimate) -> str:
    """``point [low, high]``.

    Args:
        estimate: Estimate.

    Returns:
        The formatted estimate.
    """
    if estimate.point is None:
        return "n/a"
    if estimate.low is None or estimate.high is None:
        return fmt(estimate.point)
    return f"{fmt(estimate.point)} [{fmt(estimate.low)}, {fmt(estimate.high)}]"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    return lines


def _short(value: str | None) -> str:
    return value[:12] if value else "n/a"


def _metric_rows(metrics: Sequence[Estimate]) -> list[list[str]]:
    rows = []
    for m in metrics:
        estimate = fmt_estimate(m)
        if m.lower_bound_one_sided is not None:
            estimate += f"; one-sided 95% lower bound {fmt(m.lower_bound_one_sided, 4)}"
        rows.append(
            [m.metric, estimate, m.method, str(m.n), "" if m.k is None else str(m.k), m.notes]
        )
    return rows


def _header_rows(report: EvalReport) -> list[list[str]]:
    p, h, c, b = report.provenance, report.holdout, report.counts, report.bootstrap
    status = "SEALED" if h.sealed else "open"
    count = (
        "" if h.eval_count_on_split is None else f", eval_count_on_split {h.eval_count_on_split}"
    )
    origins = ", ".join(f"{k} {v}" for k, v in h.origins.items())
    predictions = ", ".join(f"{k} ({_short(v)})" for k, v in p.prediction_files.items())
    manifests = ", ".join(f"{k} ({_short(v)})" for k, v in p.data_manifests.items()) or "none"
    return [
        ["Run", str(report.run_id)],
        ["Created", report.created_at.isoformat(timespec="seconds")],
        ["Experiment / split", f"{report.experiment} / {report.split} ({status}{count})"],
        ["System", report.system.system_id],
        ["Git SHA", p.git_sha or "unknown"],
        ["Gold", f"{p.gold_file} ({_short(p.gold_sha256)})"],
        ["Predictions", predictions],
        ["Data manifests", manifests],
        ["Analysis plan", f"{p.analysis_plan_file or 'missing'} ({_short(p.analysis_plan_sha)})"],
        ["Taxonomy / label rules", f"{p.taxonomy_version} / {p.label_rules_version}"],
        ["Bootstrap", f"B = {b.n_resamples}, seed {b.rng_seed}, level {b.level:.0%}"],
        [
            "Records",
            f"gold {c.n_gold}, scored {c.n_scored}, missing {c.n_missing}, extra {c.n_extra}, "
            f"with decision {c.n_with_decision}",
        ],
        ["Holdout", f"phase {h.phase}; origins {origins}"],
    ]


def _class_table(rows: Sequence[ClassRow]) -> list[str]:
    body = [
        [
            r.label,
            str(r.support),
            "" if r.predicted is None else str(r.predicted),
            str(r.tp),
            fmt(r.precision),
            f"{fmt(r.recall)} [{fmt(r.recall_low)}, {fmt(r.recall_high)}]",
            fmt(r.f1),
        ]
        for r in rows
    ]
    return _table(
        ("Class", "Support", "Predicted", "TP", "Precision", "Recall [95% CI]", "F1"), body
    )


def _confusion_table(matrix: ConfusionMatrix) -> list[str]:
    legend = {label: str(i) for i, label in enumerate(matrix.gold_labels, start=1)}
    columns = [legend.get(label, "inv") for label in matrix.predicted_labels]
    body = [
        [f"{legend[gold]} {gold}", *(str(v) for v in row)]
        for gold, row in zip(matrix.gold_labels, matrix.counts, strict=True)
    ]
    return _table(("gold \\ predicted", *columns), body)


def render_report(report: EvalReport, *, level: int = 1) -> str:
    """Render one report as Markdown.

    Args:
        report: Report.
        level: Heading level of the title (sections are one level deeper).

    Returns:
        Markdown text.
    """
    h1, h2 = "#" * level, "#" * (level + 1)
    lines = [
        f"{h1} {report.experiment} on {report.split}: {report.system.system_id}",
        "",
        "Estimates are `point [low, high]` at the stated level; method and n per row "
        "(evals/ANALYSIS_PLAN.md).",
        "",
        *_table(("Field", "Value"), _header_rows(report)),
        "",
        f"{h2} Metrics",
        "",
        *_table(("Metric", "Estimate", "Method", "n", "k", "Notes"), _metric_rows(report.metrics)),
    ]
    if report.gates:
        body = [
            [
                g.gate_id,
                g.metric,
                f"{g.comparator} {g.threshold:g}",
                f"{fmt(g.point)} [{fmt(g.low)}, {fmt(g.high)}]",
                {True: "pass", False: "FAIL", None: "undefined"}[g.passed]
                + (" (CI covers threshold)" if g.ci_covers_threshold else ""),
                g.source,
            ]
            for g in report.gates
        ]
        lines += ["", f"{h2} Gates", ""]
        lines += _table(("Gate", "Metric", "Threshold", "Estimate", "Result", "Source"), body)
    if report.seeds:
        body = [
            [
                s.metric,
                ", ".join(f"{k}: {fmt(v)}" for k, v in s.per_seed.items()),
                fmt(s.mean),
                f"{fmt(s.sd, 4)} [{fmt(s.sd_low, 4)}, {fmt(s.sd_high, 4)}]",
                f"{fmt(s.minimum)} to {fmt(s.maximum)}",
                fmt_estimate(s.seed_mean_ci) if s.seed_mean_ci else "",
            ]
            for s in report.seeds
        ]
        deployed = report.system.deployed_seed or "n/a"
        lines += ["", f"{h2} Seeds (deployed seed chosen on val: {deployed})", ""]
        lines += _table(
            ("Metric", "Per seed", "Mean", "SD [chi-square CI]", "Range", "Seed-mean CI"), body
        )
    for name, rows in report.per_class.items():
        lines += ["", f"{h2} Per class: {name}", "", *_class_table(rows)]
    for name, matrix in report.confusion.items():
        lines += ["", f"{h2} Confusion matrix: {name}", "", *_confusion_table(matrix)]
    validity = [[tier, str(count)] for tier, count in report.validity_counts.items()]
    lines += ["", f"{h2} Validity tiers", "", *_table(("Tier", "Count"), validity)]
    if report.notes or report.holdout.notes:
        lines += ["", f"{h2} Notes", ""]
        lines += [f"- {note}" for note in (*report.holdout.notes, *report.notes)]
    return "\n".join(lines) + "\n"


def render_index(reports: Sequence[EvalReport], *, title: str) -> str:
    """Combine several reports into one Markdown page (``baselines.md``, ``bakeoff.md``).

    Args:
        reports: Reports (typically one per experiment x split).
        title: Page title.

    Returns:
        Markdown text: a summary table, then every report.
    """
    columns = [f"{r.experiment} {r.split}: {r.system.system_id}" for r in reports]
    body = []
    for metric_id in HEADLINE_METRICS:
        cells = [r.metric(metric_id) for r in reports]
        if any(c is not None and c.point is not None for c in cells):
            body.append([metric_id, *(fmt_estimate(c) if c else "n/a" for c in cells)])
    lines = [
        f"# {title}",
        "",
        "Generated by `python -m tw_ml.eval render`; every number is `point [low, high]` "
        "(95%) with its method and n in the sections below. Splits are never pooled.",
        "",
        *_table(("Metric", *columns), body),
    ]
    for report in reports:
        lines += ["", render_report(report, level=2).rstrip("\n")]
    return "\n".join(lines) + "\n"


def render_comparison(report: ComparisonReport) -> str:
    """Render a comparison report as Markdown.

    Args:
        report: Comparison report.

    Returns:
        Markdown text.
    """
    body = [
        [
            c.hypothesis or "",
            f"{c.system_a} vs {c.system_b}",
            c.alternative,
            fmt_estimate(c.delta_macro_f1),
            fmt_estimate(c.delta_accuracy),
            fmt(c.p_randomization, 4),
            f"{fmt(c.mcnemar.p_midp, 4)} ({c.mcnemar.n10}/{c.mcnemar.n01})",
            f"{fmt(c.p_holm, 4)} ({'reject' if c.reject_holm else 'retain'})",
            c.acceptance or "",
        ]
        for c in report.comparisons
    ]
    p, h = report.provenance, report.holdout
    lines = [
        f"# Paired comparison on {report.split} ({report.family} family)",
        "",
        f"n = {report.n_items}; B = {report.bootstrap.n_resamples}, seed "
        f"{report.bootstrap.rng_seed}; Holm at alpha = {report.alpha}; "
        f"git {p.git_sha or 'unknown'}; analysis plan {_short(p.analysis_plan_sha)}; "
        f"{'SEALED' if h.sealed else 'open'} split, phase {h.phase}.",
        "",
        *_table(
            (
                "Hypothesis",
                "Systems",
                "Alternative",
                "Delta macro-F1 [95% CI]",
                "Delta accuracy [95% CI]",
                "p (randomization)",
                "McNemar mid-p (n10/n01)",
                "Holm p",
                "Acceptance",
            ),
            body,
        ),
    ]
    if report.notes:
        lines += ["", "## Notes", "", *(f"- {note}" for note in report.notes)]
    return "\n".join(lines) + "\n"
