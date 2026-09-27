"""Label QA: the 540-record random audit, the Wilson pass rule and Cohen's kappa (A-11).

Spec v1.1 §9.1 step 6 (ERPROT synthetic-data-generation D4, evaluation-statistics F2/F7):

* audit: 540 train records (15%) sampled stratified by intent x difficulty with a fixed seed,
  *before* any targeted fix. The reviewer first sees a blind sheet (ticket only) and picks the
  intent, then confirms or edits the other proposed fields;
* an audited record is an error when intent, priority, recommended_queue,
  customer_requested_human or information_sufficient is wrong, or an entity is missing or
  hallucinated; sentiment and churn disagreements are counted separately (subjective fields);
* pass only if the Wilson 95% upper bound of the error rate is below 5%, i.e. at most 17 errors
  in 540; an intent at or above 4 errors per 45 audited records gets a full re-review;
* second annotator: Cohen's kappa with a bootstrap CI; kappa < 0.80 triggers a guideline
  revision and re-review.
"""

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

from tw_ml.datagen.alloc import rng_for, stratified_sample
from tw_ml.datagen.records import DatasetRecord, RecordModel, TriageLabels
from tw_ml.datagen.taxonomy import (
    ChurnRiskValue,
    IntentValue,
    PriorityValue,
    QueueValue,
    SentimentValue,
)

Z_95: Final = 1.959963984540054
AUDIT_SIZE: Final = 540
MAX_ERROR_RATE: Final = 0.05
INTENT_REREVIEW_RATE: Final = 4 / 45
KAPPA_MIN: Final = 0.80
AUDIT_SEED: Final = 20260927
ERROR_FIELDS: Final[tuple[str, ...]] = (
    "intent",
    "priority",
    "recommended_queue",
    "customer_requested_human",
    "information_sufficient",
)
SUBJECTIVE_FIELDS: Final[tuple[str, ...]] = ("sentiment", "churn_risk")


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Args:
        k: Successes (here: errors).
        n: Trials.
        z: Normal quantile (1.96 for 95%).

    Returns:
        ``(low, high)``.

    Raises:
        ValueError: If ``n`` is not positive or ``k`` is outside ``[0, n]``.
    """
    if n <= 0 or not 0 <= k <= n:
        msg = "need n > 0 and 0 <= k <= n"
        raise ValueError(msg)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def audit_passes(errors: int, n: int = AUDIT_SIZE, max_rate: float = MAX_ERROR_RATE) -> bool:
    """The A-11 pass rule: Wilson 95% upper bound strictly below ``max_rate``.

    Args:
        errors: Errors found.
        n: Records audited.
        max_rate: Rate the upper bound must stay under.

    Returns:
        True when the audit passes.
    """
    return wilson_interval(errors, n)[1] < max_rate


def max_errors_allowed(n: int = AUDIT_SIZE, max_rate: float = MAX_ERROR_RATE) -> int:
    """Largest error count that still passes (17 for n=540).

    Args:
        n: Records audited.
        max_rate: Rate the upper bound must stay under.

    Returns:
        The largest passing ``k`` (``-1`` if even zero errors fail).
    """
    allowed = -1
    for k in range(n + 1):
        if not audit_passes(k, n, max_rate):
            break
        allowed = k
    return allowed


def audit_stratum(record: DatasetRecord) -> tuple[str, str]:
    """Audit stratum: proposed intent x difficulty (``none`` for records without a cell).

    Args:
        record: Record.

    Returns:
        The stratum key.
    """
    return record.labels.intent, record.cell.difficulty if record.cell else "none"


def audit_sample(
    records: Sequence[DatasetRecord], n: int = AUDIT_SIZE, seed: int = AUDIT_SEED
) -> list[DatasetRecord]:
    """Draw the stratified random audit sample (intent x difficulty, fixed seed).

    Args:
        records: Train records (before any targeted fix).
        n: Sample size.
        seed: Seed (record it with the audit).

    Returns:
        The sample, ordered by stratum.
    """
    return stratified_sample(
        records, key=audit_stratum, n=n, seed=seed, sort_key=lambda r: r.record_id
    )


def blind_sheet(sample: Sequence[DatasetRecord], seed: int = AUDIT_SEED) -> list[dict[str, Any]]:
    """Step 1 of the audit: the ticket only, in a shuffled order, with opaque audit ids.

    Args:
        sample: Audit sample.
        seed: Shuffle seed.

    Returns:
        Rows to review without seeing any proposed label.
    """
    rows = [
        {
            "audit_id": "",
            "record_id": r.record_id,
            "customer_tier": r.ticket.customer_tier,
            "channel": r.ticket.channel,
            "subject": r.ticket.subject,
            "message": r.ticket.message,
            "previous_messages": [
                {"author": m.author, "body": m.body} for m in r.ticket.previous_messages
            ],
            "reviewer_intent": None,
        }
        for r in sample
    ]
    rng_for(seed, "audit-order").shuffle(rows)
    for position, row in enumerate(rows, start=1):
        row["audit_id"] = f"au_{position:04d}"
    return rows


class AuditReview(RecordModel):
    """The reviewer's verdict for one audited record (``reviewer`` is a pseudonymous R-id)."""

    audit_id: str
    record_id: str
    reviewer: str = ""
    intent: IntentValue
    priority: PriorityValue
    recommended_queue: QueueValue
    customer_requested_human: bool
    information_sufficient: bool
    entities_missing: bool = False
    entities_hallucinated: bool = False
    sentiment: SentimentValue | None = None
    churn_risk: ChurnRiskValue | None = None
    notes: str = ""


@dataclass(slots=True)
class AuditResult:
    """Scored audit.

    Attributes:
        n: Records audited.
        errors: Records with at least one error.
        error_rate: ``errors / n``.
        wilson_low: Wilson 95% lower bound.
        wilson_high: Wilson 95% upper bound.
        passed: Whether the A-11 rule holds.
        max_errors_allowed: Largest passing error count for this ``n``.
        error_fields: Field to error count.
        per_intent: Proposed intent to ``(errors, audited)``.
        intents_to_rereview: Intents at or above 4/45 errors.
        subjective_disagreements: Sentiment/churn disagreements (not errors).
        missing_reviews: Sampled record ids without a review.
    """

    n: int
    errors: int
    error_rate: float
    wilson_low: float
    wilson_high: float
    passed: bool
    max_errors_allowed: int
    error_fields: dict[str, int] = field(default_factory=dict)
    per_intent: dict[str, tuple[int, int]] = field(default_factory=dict)
    intents_to_rereview: list[str] = field(default_factory=list)
    subjective_disagreements: dict[str, int] = field(default_factory=dict)
    missing_reviews: list[str] = field(default_factory=list)


def review_errors(proposed: TriageLabels, review: AuditReview) -> list[str]:
    """Fields a review marks as wrong (the error definition of ERPROT D4).

    Args:
        proposed: Proposed labels.
        review: Reviewer verdict.

    Returns:
        Wrong fields (``entities`` when an entity is missing or hallucinated).
    """
    wrong = [name for name in ERROR_FIELDS if getattr(proposed, name) != getattr(review, name)]
    if review.entities_missing or review.entities_hallucinated:
        wrong.append("entities")
    return wrong


def score_audit(
    proposed: Mapping[str, TriageLabels], reviews: Sequence[AuditReview]
) -> AuditResult:
    """Score an audit against the proposed labels.

    Args:
        proposed: Record id to proposed labels (the whole audit sample).
        reviews: Reviewer verdicts.

    Returns:
        The result, including the Wilson pass decision and re-review triggers.
    """
    fields: Counter[str] = Counter()
    subjective: Counter[str] = Counter()
    per_intent_errors: Counter[str] = Counter()
    per_intent_total: Counter[str] = Counter()
    errors = 0
    reviewed = {r.record_id: r for r in reviews if r.record_id in proposed}
    for record_id, review in reviewed.items():
        labels = proposed[record_id]
        per_intent_total[labels.intent] += 1
        wrong = review_errors(labels, review)
        if wrong:
            errors += 1
            per_intent_errors[labels.intent] += 1
            fields.update(wrong)
        for name in SUBJECTIVE_FIELDS:
            verdict = getattr(review, name)
            if verdict is not None and verdict != getattr(labels, name):
                subjective[name] += 1
    n = len(reviewed)
    low, high = wilson_interval(errors, n) if n else (0.0, 1.0)
    per_intent = {i: (per_intent_errors[i], per_intent_total[i]) for i in sorted(per_intent_total)}
    return AuditResult(
        n=n,
        errors=errors,
        error_rate=errors / n if n else 0.0,
        wilson_low=low,
        wilson_high=high,
        passed=bool(n) and high < MAX_ERROR_RATE,
        max_errors_allowed=max_errors_allowed(n) if n else -1,
        error_fields=dict(sorted(fields.items())),
        per_intent=per_intent,
        intents_to_rereview=[
            i for i, (e, t) in per_intent.items() if t and e / t >= INTENT_REREVIEW_RATE
        ],
        subjective_disagreements=dict(sorted(subjective.items())),
        missing_reviews=sorted(set(proposed) - set(reviewed)),
    )


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float:
    """Cohen's kappa for two raters on nominal labels.

    Args:
        first: Labels of rater 1.
        second: Labels of rater 2 (same items, same order).

    Returns:
        Kappa; ``nan`` when chance agreement is 1 (every label identical and constant).

    Raises:
        ValueError: If the sequences differ in length or are empty.
    """
    if len(first) != len(second) or not first:
        msg = "kappa needs two equally long, non-empty label sequences"
        raise ValueError(msg)
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / n
    left, right = Counter(first), Counter(second)
    expected = sum(left[label] * right[label] for label in left) / (n * n)
    if math.isclose(expected, 1.0):
        return math.nan
    return (observed - expected) / (1 - expected)


@dataclass(frozen=True, slots=True)
class Agreement:
    """Inter-annotator agreement summary.

    Attributes:
        n: Items double-labelled.
        kappa: Cohen's kappa.
        kappa_low: Bootstrap percentile lower bound.
        kappa_high: Bootstrap percentile upper bound.
        percent_agreement: Raw agreement.
        undefined_resamples: Bootstrap resamples where kappa was undefined.
        n_resamples: Bootstrap resamples drawn.
        seed: Bootstrap seed.
        meets_threshold: kappa >= 0.80 (otherwise revise the guidelines and re-review).
    """

    n: int
    kappa: float
    kappa_low: float
    kappa_high: float
    percent_agreement: float
    undefined_resamples: int
    n_resamples: int
    seed: int
    meets_threshold: bool


def agreement(
    first: Sequence[str],
    second: Sequence[str],
    *,
    n_resamples: int = 10_000,
    level: float = 0.95,
    seed: int = 2026,
) -> Agreement:
    """Cohen's kappa with an item-bootstrap percentile CI (ERPROT evaluation-statistics D10).

    Args:
        first: Rater 1 labels.
        second: Rater 2 labels.
        n_resamples: Bootstrap resamples.
        level: CI level.
        seed: Bootstrap seed.

    Returns:
        The agreement summary.
    """
    kappa = cohen_kappa(first, second)
    a, b = np.asarray(first), np.asarray(second)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, a.size, size=(n_resamples, a.size))
    values = np.array([cohen_kappa(a[d].tolist(), b[d].tolist()) for d in draws], dtype=np.float64)
    finite = values[~np.isnan(values)]
    tail = (1 - level) / 2
    low, high = (
        (float(np.quantile(finite, tail)), float(np.quantile(finite, 1 - tail)))
        if finite.size
        else (math.nan, math.nan)
    )
    return Agreement(
        n=a.size,
        kappa=kappa,
        kappa_low=low,
        kappa_high=high,
        percent_agreement=float(np.mean(a == b)),
        undefined_resamples=int(n_resamples - finite.size),
        n_resamples=n_resamples,
        seed=seed,
        meets_threshold=not math.isnan(kappa) and kappa >= KAPPA_MIN,
    )


def second_annotation_sample(
    records: Sequence[DatasetRecord], fraction: float = 0.2, seed: int = AUDIT_SEED
) -> list[DatasetRecord]:
    """Stratified subset for the second annotator (20% of test_synth; use 1.0 for test_hard).

    Args:
        records: Records of one split.
        fraction: Share to double-label.
        seed: Sampling seed.

    Returns:
        The subset (stratified by intent).
    """
    size = round(len(records) * fraction)
    return stratified_sample(
        records, key=lambda r: r.labels.intent, n=size, seed=seed, sort_key=lambda r: r.record_id
    )
