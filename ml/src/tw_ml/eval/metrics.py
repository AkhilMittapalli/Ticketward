"""Classification, validity and escalation metrics M-01..M-04 and M-07a..d (spec v1.1 §9.8).

Every number is a :class:`~tw_ml.eval.stats.Interval` carrying its method and ``n``:

* M-01 intent macro-F1 over the 12 intents (sklearn semantics, ``zero_division=0``), stratified
  bootstrap; intent accuracy (Wilson); ``other_unclear`` reported separately (F1, precision,
  recall);
* M-02 routing accuracy: the policy's final queue when the prediction carries a decision, else
  the model's ``recommended_queue``, against the gold queue (the scenario's gold queue when the
  gold carries a decision);
* M-03 priority exact and within-one, product-area accuracy (Wilson), sentiment and churn
  macro-F1 (stratified bootstrap), entity micro-F1 with exact type and value (ticket-cluster
  bootstrap: entities of one ticket are correlated);
* M-03c critical-category recall per class and **pooled**: model level (primary intent) always;
  system level (model primary or secondary intent, the class's forced reason, or
  ``critical_category_suspected``) when predictions carry policy decisions;
* M-04 JSON validity, first-pass, schema-repair and failure rates (validity tiers of §6.6);
* M-07a..d when predictions carry policy decisions: forced escalation with the one-sided exact
  95% lower bound, correct abstention, over-escalation, human-request detection (explicit,
  indirect, pooled).

Nothing is excluded (ANALYSIS_PLAN: exclusion rules "none"): a missing prediction or a missing
output is scored as the sentinel class ``__invalid__``, which is never correct, and a
decision-level item without a decision counts as not escalated (fail closed).
"""

import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import numpy as np

from tw_ml.datagen.labelrules import PRIORITY_ORDER, LabelRules
from tw_ml.datagen.records import EntityLabel
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.eval.data import MISSING, VALIDITY_TIERS, EvalItem, EvalSet, GoldItem, PolicyOutcome
from tw_ml.eval.stats import (
    B_DEFAULT,
    LEVEL,
    RNG_SEED,
    Alternative,
    FloatArray,
    IntArray,
    Interval,
    McNemarResult,
    RowStatistic,
    accuracy_rows,
    bootstrap,
    confusion_counts,
    encode,
    exact_lower_bound,
    macro_f1_rows,
    mcnemar,
    micro_f1_rows,
    paired_bootstrap,
    proportion,
    randomization_pvalue,
    seed_mean_bootstrap,
)

INVALID: Final = "__invalid__"
"""Prediction class of a missing or invalid output; never equal to a gold label."""
OTHER_UNCLEAR: Final = "other_unclear"
PRIORITY_RANK: Final[Mapping[str, int]] = {p: rank for rank, p in enumerate(PRIORITY_ORDER)}
CLASS_REASONS: Final[Mapping[str, str]] = {
    "security_report": "forced_category_security",
    "service_outage": "active_incident",
    "cancellation_request": "forced_category_cancellation",
    "billing_duplicate_charge": "forced_category_payment_dispute",
    "billing_payment_failure": "forced_category_payment_dispute",
}
"""The forced-review reason each critical class triggers (P2, P4, P5; spec §5.9)."""
FORCED_REASONS: Final[frozenset[str]] = frozenset(
    {
        "forced_category_refund",
        "forced_category_cancellation",
        "forced_category_payment_dispute",
        "forced_category_security",
        "forced_category_legal_threat",
        "forced_category_privacy",
        "active_incident",
    }
)
EVIDENCE_REASONS: Final[frozenset[str]] = frozenset(
    {"insufficient_evidence", "stale_evidence_only", "conflicting_evidence"}
)
SUSPECTED_REASON: Final = "critical_category_suspected"
HUMAN_REASON: Final = "customer_requested_human"
ESCALATION: Final = "human_escalation"
ABSTAIN_OR_ESCALATE: Final[frozenset[str]] = frozenset({"abstain_request_info", "human_escalation"})
DRAFT_PATHS: Final[frozenset[str]] = frozenset({"local_draft", "frontier_draft"})
SEED_METRICS: Final[tuple[str, ...]] = (
    "M-01.intent_macro_f1",
    "M-01.intent_accuracy",
    "M-02.routing_accuracy",
    "M-03.priority_accuracy",
    "M-03.entity_f1",
    "M-03c.model.pooled_recall",
    "M-04.json_validity",
)
"""Headline metrics aggregated across seeds (per-seed values, mean, SD, range)."""


@dataclass(frozen=True, slots=True)
class EvalSettings:
    """Bootstrap settings shared by every metric of a run (recorded in the report).

    Attributes:
        n_resamples: Bootstrap resamples (B).
        seed: ``numpy.random.default_rng`` seed.
        level: Confidence level.
    """

    n_resamples: int = B_DEFAULT
    seed: int = RNG_SEED
    level: float = LEVEL


@dataclass(frozen=True, slots=True)
class MetricValue:
    """One metric of a suite.

    Attributes:
        metric_id: Stable id (``M-01.intent_macro_f1``...).
        estimate: Point, interval, method and ``n``.
        lower_bound_one_sided: One-sided exact 95% lower bound (M-07a).
        notes: Caveats (absent classes, fail-closed counts...).
    """

    metric_id: str
    estimate: Interval
    lower_bound_one_sided: float | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ClassStats:
    """Per-class counts and rates (``None`` where undefined).

    Attributes:
        label: Class.
        support: Gold items of the class.
        predicted: Items predicted as the class (``None`` for system-level recall rows).
        tp: Correct items of the class (system level: caught items).
        precision: ``tp / predicted``.
        recall: ``tp / support``.
        f1: ``2 tp / (support + predicted)``.
        recall_interval: Wilson / exact interval of the recall.
    """

    label: str
    support: int
    predicted: int | None
    tp: int
    precision: float | None
    recall: float | None
    f1: float | None
    recall_interval: Interval


@dataclass(frozen=True, slots=True)
class Confusion:
    """A confusion matrix (rows: gold, columns: predicted).

    Attributes:
        gold_labels: Row labels.
        predicted_labels: Column labels (``__invalid__`` added when any output was invalid).
        counts: ``counts[i][j]`` = items with gold ``i`` predicted as ``j``.
    """

    gold_labels: tuple[str, ...]
    predicted_labels: tuple[str, ...]
    counts: tuple[tuple[int, ...], ...]


@dataclass(slots=True)
class MetricSuite:
    """Everything one system scored on one split.

    Attributes:
        n_items: Gold items scored.
        metrics: Metric id to value.
        per_class: Table name (``intent``, ``critical_model``, ``critical_system``) to rows.
        confusion: Matrix name (``intent``) to matrix.
        validity_counts: Validity tier (plus ``missing``) to count.
        decision_level: Whether any prediction carries a policy decision (M-07 computed).
        n_with_decision: Items whose prediction carries a decision.
        notes: Run-level caveats.
    """

    n_items: int
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    per_class: dict[str, tuple[ClassStats, ...]] = field(default_factory=dict)
    confusion: dict[str, Confusion] = field(default_factory=dict)
    validity_counts: dict[str, int] = field(default_factory=dict)
    decision_level: bool = False
    n_with_decision: int = 0
    notes: list[str] = field(default_factory=list)

    def add(
        self,
        metric_id: str,
        estimate: Interval,
        *,
        lower_bound: float | None = None,
        notes: str = "",
    ) -> None:
        """Record a metric.

        Args:
            metric_id: Metric id.
            estimate: Its estimate.
            lower_bound: One-sided lower bound, if any.
            notes: Caveats.
        """
        self.metrics[metric_id] = MetricValue(metric_id, estimate, lower_bound, notes)

    def point(self, metric_id: str) -> float | None:
        """Point estimate of a metric.

        Args:
            metric_id: Metric id.

        Returns:
            The point estimate, or ``None`` when absent or undefined.
        """
        value = self.metrics.get(metric_id)
        return value.estimate.point if value is not None else None


# --------------------------------------------------------------------------- helpers


def vocabulary(taxonomy: Taxonomy, enum: str) -> tuple[str, ...]:
    """An enum's values plus the ``__invalid__`` sentinel (last).

    Args:
        taxonomy: Taxonomy.
        enum: Enum name.

    Returns:
        The coding vocabulary.
    """
    return (*taxonomy.values(enum), INVALID)


def _codes(values: Sequence[str | None], vocab: tuple[str, ...]) -> IntArray:
    return encode([value if value is not None else INVALID for value in values], vocab)


def _pred_field(item: EvalItem, name: str) -> str | None:
    output = item.output
    value = getattr(output, name) if output is not None else None
    return value if isinstance(value, str) else None


def intent_codes(eval_set: EvalSet, taxonomy: Taxonomy) -> tuple[IntArray, IntArray]:
    """Gold and predicted intent codes (``__invalid__`` for missing outputs).

    Args:
        eval_set: Joined set.
        taxonomy: Taxonomy.

    Returns:
        ``(gold, pred)`` over :func:`vocabulary` of ``Intent``.
    """
    vocab = vocabulary(taxonomy, "Intent")
    gold = _codes([i.gold.labels.intent for i in eval_set.items], vocab)
    pred = _codes([_pred_field(i, "intent") for i in eval_set.items], vocab)
    return gold, pred


def macro_intents(taxonomy: Taxonomy) -> tuple[str, ...]:
    """The 12 intents of M-01 (every intent except ``other_unclear``).

    Args:
        taxonomy: Taxonomy.

    Returns:
        Intents in taxonomy order.
    """
    return tuple(i for i in taxonomy.values("Intent") if i != OTHER_UNCLEAR)


def _macro_statistic(
    gold: IntArray, pred: IntArray, vocab: tuple[str, ...], labels: Sequence[str]
) -> RowStatistic:
    n_classes, label_codes = len(vocab), encode(labels, vocab)

    def statistic(indices: IntArray) -> FloatArray:
        return macro_f1_rows(gold[indices], pred[indices], n_classes, label_codes)

    return statistic


def _accuracy_statistic(gold: IntArray, pred: IntArray) -> RowStatistic:
    def statistic(indices: IntArray) -> FloatArray:
        return accuracy_rows(gold[indices], pred[indices])

    return statistic


def _class_stats(
    gold: IntArray, pred: IntArray, vocab: tuple[str, ...], labels: Sequence[str], level: float
) -> tuple[ClassStats, ...]:
    rows = []
    for label in labels:
        code = vocab.index(label)
        is_gold, is_pred = gold == code, pred == code
        support, predicted = int(is_gold.sum()), int(is_pred.sum())
        tp = int((is_gold & is_pred).sum())
        rows.append(
            ClassStats(
                label=label,
                support=support,
                predicted=predicted,
                tp=tp,
                precision=tp / predicted if predicted else None,
                recall=tp / support if support else None,
                f1=2 * tp / (support + predicted) if support + predicted else None,
                recall_interval=proportion(tp, support, level=level),
            )
        )
    return tuple(rows)


def _confusion(
    gold: IntArray, pred: IntArray, vocab: tuple[str, ...], labels: tuple[str, ...]
) -> Confusion:
    matrix = confusion_counts(gold, pred, len(vocab))[0]
    invalid = vocab.index(INVALID)
    columns = labels + ((INVALID,) if bool((pred == invalid).any()) else ())
    counts = tuple(
        tuple(int(matrix[vocab.index(g), vocab.index(p)]) for p in columns) for g in labels
    )
    return Confusion(labels, columns, counts)


# --------------------------------------------------------------------------- M-01


def _intent_metrics(
    suite: MetricSuite, eval_set: EvalSet, taxonomy: Taxonomy, settings: EvalSettings
) -> None:
    vocab = vocabulary(taxonomy, "Intent")
    gold, pred = intent_codes(eval_set, taxonomy)
    n = gold.size
    twelve = macro_intents(taxonomy)
    absent = [
        label
        for label in twelve
        if not bool((gold == vocab.index(label)).any() or (pred == vocab.index(label)).any())
    ]
    suite.add(
        "M-01.intent_macro_f1",
        bootstrap(
            _macro_statistic(gold, pred, vocab, twelve),
            n,
            strata=gold,
            n_resamples=settings.n_resamples,
            seed=settings.seed,
            level=settings.level,
        ),
        notes=(f"absent classes scored 0 (zero_division=0): {', '.join(absent)}" if absent else ""),
    )
    suite.add(
        "M-01.intent_accuracy", proportion(int((gold == pred).sum()), n, level=settings.level)
    )
    labels = tuple(taxonomy.values("Intent"))
    rows = _class_stats(gold, pred, vocab, labels, settings.level)
    suite.per_class["intent"] = rows
    suite.confusion["intent"] = _confusion(gold, pred, vocab, labels)
    other = next(row for row in rows if row.label == OTHER_UNCLEAR)
    suite.add(
        "M-01.other_unclear_f1",
        bootstrap(
            _macro_statistic(gold, pred, vocab, (OTHER_UNCLEAR,)),
            n,
            strata=gold,
            n_resamples=settings.n_resamples,
            seed=settings.seed,
            level=settings.level,
        ),
        notes="reported separately; not part of the 12-intent macro-F1",
    )
    suite.add("M-01.other_unclear_recall", other.recall_interval)
    suite.add(
        "M-01.other_unclear_precision",
        proportion(other.tp, other.predicted or 0, level=settings.level),
    )


# --------------------------------------------------------------------------- M-02


def gold_queue(gold: GoldItem) -> str:
    """The gold queue: the scenario's gold decision queue, else the labels' queue.

    Args:
        gold: Gold item.

    Returns:
        A queue value.
    """
    if gold.decision is not None and gold.decision.queue is not None:
        return gold.decision.queue
    return gold.labels.recommended_queue


def _routing_metric(suite: MetricSuite, eval_set: EvalSet, settings: EvalSettings) -> None:
    correct = final = model = 0
    for item in eval_set.items:
        decision, output = item.decision, item.output
        if decision is not None and decision.final_queue is not None:
            predicted: str | None = decision.final_queue
            final += 1
        elif output is not None:
            predicted = output.recommended_queue
            model += 1
        else:
            predicted = None
        correct += predicted == gold_queue(item.gold)
    none = len(eval_set.items) - final - model
    suite.add(
        "M-02.routing_accuracy",
        proportion(correct, len(eval_set.items), level=settings.level),
        notes=f"policy final queue for {final}, model queue for {model}, none for {none}",
    )


# --------------------------------------------------------------------------- M-03


def _field_metrics(
    suite: MetricSuite, eval_set: EvalSet, taxonomy: Taxonomy, settings: EvalSettings
) -> None:
    items, n, level = eval_set.items, len(eval_set.items), settings.level
    exact = within = area = 0
    for item in items:
        predicted = _pred_field(item, "priority")
        gold = item.gold.labels.priority
        exact += predicted == gold
        within += predicted is not None and abs(PRIORITY_RANK[predicted] - PRIORITY_RANK[gold]) <= 1
        area += _pred_field(item, "product_area") == item.gold.labels.product_area
    suite.add("M-03.priority_accuracy", proportion(exact, n, level=level))
    suite.add("M-03.priority_within_one", proportion(within, n, level=level))
    suite.add("M-03.product_area_accuracy", proportion(area, n, level=level))
    for metric_id, name, enum in (
        ("M-03.sentiment_macro_f1", "sentiment", "Sentiment"),
        ("M-03.churn_macro_f1", "churn_risk", "ChurnRisk"),
    ):
        vocab = vocabulary(taxonomy, enum)
        gold_codes = _codes([getattr(i.gold.labels, name) for i in items], vocab)
        pred_codes = _codes([_pred_field(i, name) for i in items], vocab)
        suite.add(
            metric_id,
            bootstrap(
                _macro_statistic(gold_codes, pred_codes, vocab, taxonomy.values(enum)),
                n,
                strata=gold_codes,
                n_resamples=settings.n_resamples,
                seed=settings.seed,
                level=level,
            ),
        )


def entity_key(entity: EntityLabel) -> tuple[str, str]:
    """Matching key of an entity: exact type, value after NFKC and trimming.

    Args:
        entity: Entity.

    Returns:
        ``(type, value)``.
    """
    return entity.type, unicodedata.normalize("NFKC", entity.value).strip()


def entity_counts(
    gold: Sequence[EntityLabel], predicted: Sequence[EntityLabel]
) -> tuple[int, int, int]:
    """Multiset match of one ticket's entities.

    Args:
        gold: Gold entities.
        predicted: Predicted entities.

    Returns:
        ``(tp, fp, fn)``.
    """
    g, p = Counter(map(entity_key, gold)), Counter(map(entity_key, predicted))
    tp = sum((g & p).values())
    return tp, sum(p.values()) - tp, sum(g.values()) - tp


def _ratio_statistic(counts: IntArray, extra_column: int) -> RowStatistic:
    def statistic(indices: IntArray) -> FloatArray:
        totals = counts[indices].sum(axis=1).astype(np.float64)
        tp, denominator = totals[:, 0], totals[:, 0] + totals[:, extra_column]
        return np.divide(tp, denominator, out=np.full_like(tp, np.nan), where=denominator > 0)

    return statistic


def _entity_metrics(suite: MetricSuite, eval_set: EvalSet, settings: EvalSettings) -> None:
    rows = [
        entity_counts(item.gold.labels.entities, item.output.entities if item.output else ())
        for item in eval_set.items
    ]
    counts = np.asarray(rows, dtype=np.int64).reshape(-1, 3)
    n = counts.shape[0]
    tp, fp, fn = (int(v) for v in counts.sum(axis=0))
    notes = f"gold entities {tp + fn}, predicted {tp + fp}, matched {tp}; ticket-cluster bootstrap"

    def f1(indices: IntArray) -> FloatArray:
        return micro_f1_rows(counts, indices)

    for metric_id, statistic in (
        ("M-03.entity_f1", f1),
        ("M-03.entity_precision", _ratio_statistic(counts, 1)),
        ("M-03.entity_recall", _ratio_statistic(counts, 2)),
    ):
        suite.add(
            metric_id,
            bootstrap(
                statistic,
                n,
                n_resamples=settings.n_resamples,
                seed=settings.seed,
                level=settings.level,
                label="ticket-cluster-percentile-bootstrap",
            ),
            notes=notes,
        )


# --------------------------------------------------------------------------- M-03c


def critical_intents(taxonomy: Taxonomy, rules: LabelRules) -> tuple[str, ...]:
    """The five critical intents in taxonomy order (spec §5.1).

    Args:
        taxonomy: Taxonomy.
        rules: Label rules (critical set).

    Returns:
        Critical intents.
    """
    return tuple(i for i in taxonomy.values("Intent") if rules.is_critical(i))


def caught_by_system(item: EvalItem, intent: str) -> bool:
    """Whether the system flagged a critical class for forced human review.

    The policy engine evaluates forced rules on the union of primary and secondary intents, so
    a secondary intent counts; so do the class's forced reason and ``critical_category_suspected``
    (N6), which forces human review without naming the class.

    Args:
        item: Joined item.
        intent: Critical intent.

    Returns:
        True when caught.
    """
    output, decision = item.output, item.decision
    if output is not None and intent in {output.intent, *output.secondary_intents}:
        return True
    if decision is None:
        return False
    reasons = set(decision.escalation_reasons)
    return CLASS_REASONS[intent] in reasons or (
        SUSPECTED_REASON in reasons and decision.needs_human_review
    )


def _critical_metrics(
    suite: MetricSuite,
    eval_set: EvalSet,
    taxonomy: Taxonomy,
    rules: LabelRules,
    settings: EvalSettings,
) -> None:
    vocab = vocabulary(taxonomy, "Intent")
    gold, pred = intent_codes(eval_set, taxonomy)
    classes = critical_intents(taxonomy, rules)
    model_rows = _class_stats(gold, pred, vocab, classes, settings.level)
    suite.per_class["critical_model"] = model_rows
    for row in model_rows:
        suite.add(f"M-03c.model.{row.label}_recall", row.recall_interval)
    suite.add(
        "M-03c.model.pooled_recall",
        proportion(
            sum(r.tp for r in model_rows), sum(r.support for r in model_rows), level=settings.level
        ),
        notes="primary intent == gold primary intent, pooled over the 5 critical classes",
    )
    if not suite.decision_level:
        return
    system_rows = []
    for intent in classes:
        members = [item for item in eval_set.items if item.gold.labels.intent == intent]
        caught = sum(caught_by_system(item, intent) for item in members)
        interval = proportion(caught, len(members), level=settings.level)
        system_rows.append(
            ClassStats(
                intent,
                len(members),
                None,
                caught,
                None,
                interval.point,
                None,
                interval,
            )
        )
        suite.add(f"M-03c.system.{intent}_recall", interval)
    suite.per_class["critical_system"] = tuple(system_rows)
    suite.add(
        "M-03c.system.pooled_recall",
        proportion(
            sum(r.tp for r in system_rows),
            sum(r.support for r in system_rows),
            level=settings.level,
        ),
        notes="model primary/secondary intent, the class's forced reason or N6, pooled",
    )


# --------------------------------------------------------------------------- M-04


def _validity_metrics(suite: MetricSuite, eval_set: EvalSet, settings: EvalSettings) -> None:
    counts = Counter(
        item.prediction.validity if item.prediction is not None else MISSING
        for item in eval_set.items
    )
    suite.validity_counts = {tier: counts.get(tier, 0) for tier in (*VALIDITY_TIERS, MISSING)}
    n, level = len(eval_set.items), settings.level
    first, l1, l2 = counts["first_pass"], counts["repaired_l1"], counts["repaired_l2"]
    suite.add(
        "M-04.json_validity",
        proportion(first + l1 + l2, n, level=level),
        notes="(first_pass + repaired_l1 + repaired_l2) / total",
    )
    suite.add("M-04.first_pass", proportion(first, n, level=level))
    suite.add("M-04.schema_repair", proportion(l1 + l2, n, level=level))
    suite.add(
        "M-04.failed",
        proportion(counts["failed_fallback"] + counts[MISSING], n, level=level),
        notes="failed_fallback plus missing predictions",
    )


# --------------------------------------------------------------------------- M-07


def is_forced(gold: GoldItem, rules: LabelRules) -> bool:
    """Gold forced-category ticket (S-03): a forced-review intent, a legal threat or a gold reason.

    Args:
        gold: Gold item.
        rules: Label rules (forced-review intents).

    Returns:
        True when the ticket must reach ``human_escalation``.
    """
    intents = {gold.labels.intent, *gold.labels.secondary_intents}
    if intents & rules.forced_review_intents or gold.legal_threat:
        return True
    return gold.decision is not None and bool(
        set(gold.decision.escalation_reasons) & FORCED_REASONS
    )


def is_unanswerable(gold: GoldItem) -> bool:
    """Gold needs-info or no-evidence ticket (M-07b population).

    Args:
        gold: Gold item.

    Returns:
        True when the correct behaviour is to abstain or escalate.
    """
    labels = gold.labels
    if not labels.information_sufficient or labels.intent == OTHER_UNCLEAR or gold.needs_info:
        return True
    decision = gold.decision
    return decision is not None and (
        decision.policy_decision == "abstain_request_info"
        or bool(set(decision.escalation_reasons) & EVIDENCE_REASONS)
    )


def is_routine(gold: GoldItem, rules: LabelRules) -> bool:
    """Gold routine ticket (M-07c population): nothing requires a human decision.

    Without a gold decision this is an approximation (no forced category, no human request,
    answerable); evidence-gate escalations (P9) then count as over-escalation.

    Args:
        gold: Gold item.
        rules: Label rules.

    Returns:
        True for routine tickets.
    """
    if is_forced(gold, rules) or gold.labels.customer_requested_human or is_unanswerable(gold):
        return False
    path = gold.decision.policy_decision if gold.decision is not None else None
    return path is None or path in DRAFT_PATHS


def _decision_rate(
    suite: MetricSuite,
    metric_id: str,
    members: Sequence[EvalItem],
    hit: Callable[[PolicyOutcome], bool],
    settings: EvalSettings,
    *,
    one_sided: bool = False,
    notes: str = "",
) -> None:
    k = sum(item.decision is not None and hit(item.decision) for item in members)
    n = len(members)
    without = sum(item.decision is None for item in members)
    caveat = f"{without} items without a decision count as misses (fail closed)" if without else ""
    suite.add(
        metric_id,
        proportion(k, n, level=settings.level),
        lower_bound=exact_lower_bound(k, n, level=settings.level) if one_sided and n else None,
        notes="; ".join(part for part in (notes, caveat) if part),
    )


def _escalation_metrics(
    suite: MetricSuite, eval_set: EvalSet, rules: LabelRules, settings: EvalSettings
) -> None:
    if not suite.decision_level:
        suite.notes.append("M-07a..d not computed: no prediction carries a policy decision")
        return
    items = eval_set.items

    def escalated(decision: PolicyOutcome) -> bool:
        return decision.policy_decision == ESCALATION

    def detected(decision: PolicyOutcome) -> bool:
        return HUMAN_REASON in decision.escalation_reasons

    _decision_rate(
        suite,
        "M-07a.forced_escalation",
        [i for i in items if is_forced(i.gold, rules)],
        escalated,
        settings,
        one_sided=True,
        notes="gate 1.00; published with n and the one-sided exact 95% lower bound",
    )
    _decision_rate(
        suite,
        "M-07b.correct_abstention",
        [i for i in items if is_unanswerable(i.gold)],
        lambda d: d.policy_decision in ABSTAIN_OR_ESCALATE,
        settings,
    )
    _decision_rate(
        suite,
        "M-07c.over_escalation",
        [i for i in items if is_routine(i.gold, rules)],
        escalated,
        settings,
        notes="lower is better",
    )
    requests = [i for i in items if i.gold.labels.customer_requested_human]
    unknown = sum(i.gold.human_request_kind not in {"direct", "indirect"} for i in requests)
    for metric_id, kind in (
        ("M-07d.human_request_recall_explicit", "direct"),
        ("M-07d.human_request_recall_indirect", "indirect"),
    ):
        members = [i for i in requests if i.gold.human_request_kind == kind]
        _decision_rate(suite, metric_id, members, detected, settings)
    _decision_rate(
        suite,
        "M-07d.human_request_recall",
        requests,
        detected,
        settings,
        notes=f"all requests; {unknown} without a direct/indirect tag" if unknown else "",
    )
    _decision_rate(
        suite,
        "M-07d.false_positive_rate",
        [i for i in items if not i.gold.labels.customer_requested_human],
        detected,
        settings,
        notes="customer_requested_human reason on tickets without a request; lower is better",
    )


# --------------------------------------------------------------------------- entry points


def evaluate(
    eval_set: EvalSet,
    taxonomy: Taxonomy,
    rules: LabelRules,
    settings: EvalSettings | None = None,
) -> MetricSuite:
    """Score one system on one split.

    Args:
        eval_set: Gold joined with the system's predictions.
        taxonomy: Taxonomy (label vocabularies).
        rules: Label rules (critical and forced-review sets).
        settings: Bootstrap settings (default B = 10,000, seed 2026).

    Returns:
        The metric suite.
    """
    settings = settings or EvalSettings()
    suite = MetricSuite(n_items=len(eval_set.items))
    if not eval_set.items:
        suite.notes.append("no gold items: every metric is undefined")
        return suite
    suite.n_with_decision = eval_set.n_with_decision
    suite.decision_level = suite.n_with_decision > 0
    _intent_metrics(suite, eval_set, taxonomy, settings)
    _routing_metric(suite, eval_set, settings)
    _field_metrics(suite, eval_set, taxonomy, settings)
    _entity_metrics(suite, eval_set, settings)
    _critical_metrics(suite, eval_set, taxonomy, rules, settings)
    _validity_metrics(suite, eval_set, settings)
    _escalation_metrics(suite, eval_set, rules, settings)
    if eval_set.missing:
        suite.notes.append(
            f"{len(eval_set.missing)} gold records have no prediction; scored as invalid"
        )
    if eval_set.extra:
        suite.notes.append(f"{len(eval_set.extra)} predictions have no gold record; ignored")
    return suite


def _same_records(sets: Sequence[EvalSet]) -> None:
    orders = {tuple(item.record_id for item in s.items) for s in sets}
    if len(orders) != 1:
        msg = "paired statistics need every system scored on the same gold records"
        raise ValueError(msg)


def seed_mean_macro_f1(
    eval_sets: Sequence[EvalSet], taxonomy: Taxonomy, settings: EvalSettings | None = None
) -> Interval:
    """Two-level bootstrap CI of the seed-mean intent macro-F1 (ERPROT D4).

    Args:
        eval_sets: One joined set per seed (same gold records).
        taxonomy: Taxonomy.
        settings: Bootstrap settings.

    Returns:
        The seed-mean estimate.
    """
    settings = settings or EvalSettings()
    _same_records(eval_sets)
    vocab, labels = vocabulary(taxonomy, "Intent"), macro_intents(taxonomy)
    gold, _ = intent_codes(eval_sets[0], taxonomy)
    statistics = [
        _macro_statistic(gold, intent_codes(s, taxonomy)[1], vocab, labels) for s in eval_sets
    ]
    return seed_mean_bootstrap(
        statistics,
        gold.size,
        strata=gold,
        n_resamples=settings.n_resamples,
        seed=settings.seed,
        level=settings.level,
    )


@dataclass(frozen=True, slots=True)
class SystemComparison:
    """Paired comparison of system A against system B on the same records (ERPROT D3).

    Attributes:
        system_a: System A id(s).
        system_b: System B id(s).
        n: Records.
        alternative: ``greater`` (A > B) or ``two-sided``.
        macro_f1_a: A's intent macro-F1.
        macro_f1_b: B's intent macro-F1.
        delta_macro_f1: ``A - B`` with the paired stratified bootstrap CI.
        delta_accuracy: ``A - B`` intent accuracy with the paired stratified bootstrap CI.
        p_randomization: Approximate-randomization p-value of the macro-F1 difference.
        mcnemar: McNemar exact / mid-p on per-ticket intent correctness.
    """

    system_a: str
    system_b: str
    n: int
    alternative: Alternative
    macro_f1_a: float | None
    macro_f1_b: float | None
    delta_macro_f1: Interval
    delta_accuracy: Interval
    p_randomization: float
    mcnemar: McNemarResult


def compare_systems(
    a: EvalSet,
    b: EvalSet,
    taxonomy: Taxonomy,
    settings: EvalSettings | None = None,
    *,
    alternative: Alternative = "two-sided",
) -> SystemComparison:
    """Compare two systems on intent classification with the paired protocol.

    Args:
        a: System A joined with gold.
        b: System B joined with the same gold.
        taxonomy: Taxonomy.
        settings: Bootstrap and randomization settings (same B and seed for both).
        alternative: ``greater`` tests A > B (pre-registered one-sided hypotheses).

    Returns:
        The comparison.

    Raises:
        ValueError: If the sets do not cover the same records or are empty.
    """
    settings = settings or EvalSettings()
    _same_records((a, b))
    if not a.items:
        msg = "cannot compare systems on an empty gold set"
        raise ValueError(msg)
    vocab, labels = vocabulary(taxonomy, "Intent"), macro_intents(taxonomy)
    gold, pred_a = intent_codes(a, taxonomy)
    _, pred_b = intent_codes(b, taxonomy)
    macro_a = _macro_statistic(gold, pred_a, vocab, labels)
    macro_b = _macro_statistic(gold, pred_b, vocab, labels)
    n_classes, label_codes = len(vocab), encode(labels, vocab)

    def metric(gold_rows: IntArray, pred_rows: IntArray) -> FloatArray:
        return macro_f1_rows(gold_rows, pred_rows, n_classes, label_codes)

    def paired(statistic_a: RowStatistic, statistic_b: RowStatistic) -> Interval:
        return paired_bootstrap(
            statistic_a,
            statistic_b,
            gold.size,
            strata=gold,
            n_resamples=settings.n_resamples,
            seed=settings.seed,
            level=settings.level,
        )

    identity = np.arange(gold.size, dtype=np.int64)[None, :]
    return SystemComparison(
        system_a=", ".join(a.system_ids) or "(none)",
        system_b=", ".join(b.system_ids) or "(none)",
        n=int(gold.size),
        alternative=alternative,
        macro_f1_a=float(macro_a(identity)[0]),
        macro_f1_b=float(macro_b(identity)[0]),
        delta_macro_f1=paired(macro_a, macro_b),
        delta_accuracy=paired(_accuracy_statistic(gold, pred_a), _accuracy_statistic(gold, pred_b)),
        p_randomization=randomization_pvalue(
            gold,
            pred_a,
            pred_b,
            metric,
            n_resamples=settings.n_resamples,
            seed=settings.seed,
            alternative=alternative,
        ),
        mcnemar=mcnemar((pred_a == gold).tolist(), (pred_b == gold).tolist()),
    )
