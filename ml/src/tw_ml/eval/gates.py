"""Acceptance gates of spec v1.1 §9.8 and the phase exits of §16, as data.

Gates are decisions, not tests (ERPROT evaluation-statistics D8): a gate passes on the point
estimate and is always published with its CI. ``ci_covers_threshold`` marks the outcomes the
narrative must call inconclusive (a miss still blocks promotion unless an ADR waives it). A
gate applies only to its splits and experiments, so P2 runs on val and ``hard_dev`` meet only
the phase gates that name those splits.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from tw_ml.eval.stats import Interval

Comparator = Literal[">=", "<=", "=="]
_CRITICAL: Final[tuple[str, ...]] = (
    "billing_duplicate_charge",
    "billing_payment_failure",
    "cancellation_request",
    "service_outage",
    "security_report",
)
_TOLERANCE: Final = 1e-12


@dataclass(frozen=True, slots=True)
class Gate:
    """One acceptance threshold.

    Attributes:
        gate_id: Stable id.
        metric_id: Metric the gate reads.
        comparator: ``>=``, ``<=`` or ``==``.
        threshold: Threshold on the point estimate.
        splits: Splits the gate applies to.
        experiments: Experiments the gate applies to.
        source: Spec reference.
    """

    gate_id: str
    metric_id: str
    comparator: Comparator
    threshold: float
    splits: frozenset[str]
    experiments: frozenset[str]
    source: str

    def applies(self, split: str, experiment: str) -> bool:
        """Return whether the gate applies to a run.

        Args:
            split: Evaluated split.
            experiment: Experiment id (E1..E6).

        Returns:
            True when both match.
        """
        return split in self.splits and experiment in self.experiments

    def holds(self, value: float) -> bool:
        """Compare a value with the threshold.

        Args:
            value: Point estimate.

        Returns:
            True when the comparison holds.
        """
        if self.comparator == ">=":
            return value >= self.threshold - _TOLERANCE
        if self.comparator == "<=":
            return value <= self.threshold + _TOLERANCE
        return math.isclose(value, self.threshold, abs_tol=_TOLERANCE)


def _gate(
    gate_id: str,
    metric_id: str,
    comparator: Comparator,
    threshold: float,
    splits: Iterable[str],
    experiments: Iterable[str],
    source: str,
) -> Gate:
    return Gate(
        gate_id, metric_id, comparator, threshold, frozenset(splits), frozenset(experiments), source
    )


_TEST: Final = ("test_synth",)
_HARD: Final = ("hard_final",)
_MODEL: Final = ("E4", "E5")

GATES: Final[tuple[Gate, ...]] = (
    _gate("G-M01-test", "M-01.intent_macro_f1", ">=", 0.85, _TEST, ("E4",), "§9.8 M-01"),
    _gate("G-M01-hard", "M-01.intent_macro_f1", ">=", 0.70, _HARD, ("E4",), "§9.8 M-01"),
    _gate("G-M02-test", "M-02.routing_accuracy", ">=", 0.90, _TEST, ("E5",), "§9.8 M-02"),
    _gate("G-M02-hard", "M-02.routing_accuracy", ">=", 0.80, _HARD, ("E5",), "§9.8 M-02"),
    _gate("G-M03-priority", "M-03.priority_accuracy", ">=", 0.80, _TEST, _MODEL, "§9.8 M-03"),
    _gate("G-M03-entity", "M-03.entity_f1", ">=", 0.80, _TEST, _MODEL, "§9.8 M-03"),
    _gate(
        "G-M03c-pooled-test",
        "M-03c.system.pooled_recall",
        ">=",
        0.95,
        _TEST,
        ("E5",),
        "§9.8 M-03c (A-10 pooled gate)",
    ),
    *(
        _gate(
            f"G-M03c-{intent}-test",
            f"M-03c.system.{intent}_recall",
            ">=",
            0.90,
            _TEST,
            ("E5",),
            "§9.8 M-03c (each class)",
        )
        for intent in _CRITICAL
    ),
    *(
        _gate(
            f"G-M03c-model-{intent}-test",
            f"M-03c.model.{intent}_recall",
            ">=",
            0.90,
            _TEST,
            ("E4",),
            "§9.8 M-03c (E4 each class)",
        )
        for intent in _CRITICAL
    ),
    _gate(
        "G-M03c-pooled-hard",
        "M-03c.system.pooled_recall",
        ">=",
        0.90,
        _HARD,
        ("E5",),
        "§9.8 M-03c (hard_final pooled)",
    ),
    _gate(
        "G-M04-validity", "M-04.json_validity", ">=", 0.995, (*_TEST, *_HARD), _MODEL, "§9.8 M-04"
    ),
    _gate("G-M04-first-pass", "M-04.first_pass", ">=", 0.98, (*_TEST, *_HARD), _MODEL, "§9.8 M-04"),
    _gate("G-M04-repair", "M-04.schema_repair", "<=", 0.02, (*_TEST, *_HARD), _MODEL, "§9.8 M-04"),
    _gate("G-M04-P3", "M-04.json_validity", ">=", 0.99, ("val",), ("E4",), "§16 P3 exit (A-27)"),
    _gate(
        "G-M07a",
        "M-07a.forced_escalation",
        "==",
        1.0,
        (*_TEST, *_HARD, "hard_dev", "smoke"),
        ("E5",),
        "§9.8 M-07a; §9.10 smoke; §16 P6 exit (hard_dev)",
    ),
    _gate("G-M07b-test", "M-07b.correct_abstention", ">=", 0.90, _TEST, ("E5",), "§9.8 M-07b"),
    _gate("G-M07b-hard", "M-07b.correct_abstention", ">=", 0.85, _HARD, ("E5",), "§9.8 M-07b"),
    _gate("G-M07c", "M-07c.over_escalation", "<=", 0.15, _TEST, ("E5",), "§9.8 M-07c"),
    _gate(
        "G-M07d-explicit",
        "M-07d.human_request_recall_explicit",
        "==",
        1.0,
        _TEST,
        ("E5",),
        "§9.8 M-07d",
    ),
    _gate(
        "G-M07d-indirect",
        "M-07d.human_request_recall_indirect",
        ">=",
        0.90,
        _TEST,
        ("E5",),
        "§9.8 M-07d",
    ),
)
"""Every single-system gate. Comparative gates (E4 - E3 >= +0.10, E4 > E1) live in ``compare``."""

E4_MINUS_E3_MIN: Final = 0.10
"""M-01 acceptance: E4 - E3 macro-F1 point estimate (§9.8; the P3 exit on val)."""


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """A gate evaluated on one run.

    Attributes:
        gate: The gate.
        estimate: The metric's estimate (``None`` when the metric was not computed).
        passed: Whether the point estimate meets the threshold (``None`` when undefined).
        ci_covers_threshold: Whether the CI contains the threshold (inconclusive outcome).
    """

    gate: Gate
    estimate: Interval | None
    passed: bool | None
    ci_covers_threshold: bool | None


def evaluate_gates(
    estimates: Mapping[str, Interval],
    split: str,
    experiment: str,
    gates: Iterable[Gate] = GATES,
) -> list[GateOutcome]:
    """Evaluate every gate that applies to a run.

    Args:
        estimates: Metric id to estimate.
        split: Evaluated split.
        experiment: Experiment id.
        gates: Gate table.

    Returns:
        Outcomes of the applicable gates, in table order.
    """
    outcomes: list[GateOutcome] = []
    for gate in gates:
        if not gate.applies(split, experiment):
            continue
        estimate = estimates.get(gate.metric_id)
        point = estimate.point if estimate is not None else None
        if estimate is None or point is None:
            outcomes.append(GateOutcome(gate, estimate, None, None))
            continue
        covers = (
            estimate.low <= gate.threshold <= estimate.high
            if estimate.low is not None and estimate.high is not None
            else None
        )
        outcomes.append(GateOutcome(gate, estimate, gate.holds(point), covers))
    return outcomes
