"""Label QA math: Wilson pass rule, Cohen's kappa (vs scikit-learn), audit sampling and scoring."""

import math
from collections import Counter
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest
from sklearn.metrics import cohen_kappa_score

from tw_ml.datagen.matrix import GenerationPlan
from tw_ml.datagen.qa import (
    AuditReview,
    agreement,
    audit_passes,
    audit_sample,
    audit_stratum,
    blind_sheet,
    cohen_kappa,
    max_errors_allowed,
    review_errors,
    score_audit,
    second_annotation_sample,
    wilson_interval,
)
from tw_ml.datagen.records import DatasetRecord, TicketPayload, TriageLabels

# --------------------------------------------------------------------------- Wilson


def test_wilson_reference_values() -> None:
    low, high = wilson_interval(57, 60)  # ERPROT evaluation-statistics F2
    assert low == pytest.approx(0.863, abs=0.001)
    assert high == pytest.approx(0.983, abs=0.001)
    low, high = wilson_interval(17, 540)
    assert low == pytest.approx(0.020, abs=0.001)
    assert high < 0.05
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == pytest.approx(1.0)


def test_a11_pass_rule_is_17_of_540() -> None:
    assert max_errors_allowed(540) == 17
    assert audit_passes(17, 540)
    assert not audit_passes(18, 540)
    assert max_errors_allowed(45) == -1  # a per-intent < 5% claim is impossible at n=45
    assert not audit_passes(0, 45)


def test_wilson_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="n > 0"):
        wilson_interval(1, 0)
    with pytest.raises(ValueError, match="n > 0"):
        wilson_interval(5, 4)


# --------------------------------------------------------------------------- kappa


@pytest.mark.parametrize("seed", range(5))
def test_kappa_matches_scikit_learn(seed: int) -> None:
    rng = np.random.default_rng(seed)
    labels = ["bug_report", "how_to_question", "refund_request", "security_report"]
    first = rng.choice(labels, size=120).tolist()
    second = [a if rng.random() < 0.7 else str(rng.choice(labels)) for a in first]
    assert cohen_kappa(first, second) == pytest.approx(cohen_kappa_score(first, second))


def test_kappa_edge_cases() -> None:
    assert cohen_kappa(["a", "b"], ["a", "b"]) == pytest.approx(1.0)
    assert math.isnan(cohen_kappa(["a", "a"], ["a", "a"]))
    with pytest.raises(ValueError, match="equally long"):
        cohen_kappa(["a"], ["a", "b"])
    with pytest.raises(ValueError, match="equally long"):
        cohen_kappa([], [])


def test_agreement_bootstrap() -> None:
    first = ["x", "y", "z", "x", "y", "z", "x", "y", "z", "x"] * 6
    second = first[:50] + ["x"] * 10
    result = agreement(first, second, n_resamples=400, seed=11)
    assert result == agreement(first, second, n_resamples=400, seed=11)
    assert result.kappa_low <= result.kappa <= result.kappa_high
    assert result.n == 60
    assert result.percent_agreement == pytest.approx(np.mean(np.array(first) == np.array(second)))
    assert result.meets_threshold is (result.kappa >= 0.80)
    constant = agreement(["a"] * 5, ["a"] * 5, n_resamples=50)
    assert math.isnan(constant.kappa)
    assert not constant.meets_threshold
    assert constant.undefined_resamples == 50


# --------------------------------------------------------------------------- audit


@pytest.fixture
def audit_records(
    train_plan: GenerationPlan,
    make_ticket: Callable[..., TicketPayload],
    make_labels: Callable[..., TriageLabels],
    make_record: Callable[..., DatasetRecord],
) -> list[DatasetRecord]:
    ticket = make_ticket()
    records = []
    for cell in train_plan.cells[:600]:
        labels = make_labels(intent=cell.intent)
        records.append(
            make_record(
                ticket=ticket,
                labels=labels,
                cell=cell,
                record_id=f"tr_{cell.seq:05d}",
                cell_id=cell.cell_id,
            )
        )
    return records


def test_audit_sample_is_stratified_and_deterministic(audit_records: list[DatasetRecord]) -> None:
    sample = audit_sample(audit_records, n=150, seed=7)
    assert len(sample) == len({r.record_id for r in sample}) == 150
    assert sample == audit_sample(list(reversed(audit_records)), n=150, seed=7)
    assert sample != audit_sample(audit_records, n=150, seed=8)
    population = Counter(audit_stratum(r) for r in audit_records)
    drawn = Counter(audit_stratum(r) for r in sample)
    for stratum, count in drawn.items():
        assert abs(count - 150 * population[stratum] / len(audit_records)) < 1.0


def test_blind_sheet_hides_every_label(audit_records: list[DatasetRecord]) -> None:
    sheet = blind_sheet(audit_records[:30], seed=3)
    assert [row["audit_id"] for row in sheet] == [f"au_{i:04d}" for i in range(1, 31)]
    assert {row["record_id"] for row in sheet} == {r.record_id for r in audit_records[:30]}
    for row in sheet:
        assert set(row) == {
            "audit_id",
            "record_id",
            "customer_tier",
            "channel",
            "subject",
            "message",
            "previous_messages",
            "reviewer_intent",
        }
        assert row["reviewer_intent"] is None


def _review(record: DatasetRecord, **changes: Any) -> AuditReview:
    labels = record.labels
    values: dict[str, Any] = {
        "audit_id": "au_0001",
        "record_id": record.record_id,
        "reviewer": "R-owner",
        "intent": labels.intent,
        "priority": labels.priority,
        "recommended_queue": labels.recommended_queue,
        "customer_requested_human": labels.customer_requested_human,
        "information_sufficient": labels.information_sufficient,
        "sentiment": labels.sentiment,
        "churn_risk": labels.churn_risk,
    }
    values.update(changes)
    return AuditReview.model_validate(values)


def test_score_audit_counts_errors_and_triggers(audit_records: list[DatasetRecord]) -> None:
    sample = [r for r in audit_records if r.labels.intent == "bug_report"][:45] + audit_records[:10]
    proposals = {r.record_id: r.labels for r in sample}
    reviews = [_review(r) for r in sample[:-1]]  # one record left unreviewed
    for index in range(4):
        reviews[index] = _review(sample[index], priority="urgent")
    reviews[4] = _review(sample[4], entities_hallucinated=True, sentiment="angry")
    result = score_audit(proposals, reviews)
    assert result.n == len(sample) - 1
    assert result.errors == 5
    assert result.error_fields == {"entities": 1, "priority": 4}
    assert result.subjective_disagreements == {"sentiment": 1}
    assert "bug_report" in result.intents_to_rereview  # 5 of 45 >= 4/45
    assert result.missing_reviews == [sample[-1].record_id]
    assert result.max_errors_allowed == max_errors_allowed(result.n)
    assert result.passed is (result.wilson_high < 0.05)


def test_score_audit_pass_and_empty(audit_records: list[DatasetRecord]) -> None:
    sample = audit_sample(audit_records, n=540, seed=1)
    reviews = [_review(r) for r in sample]
    for index in range(10):
        reviews[index] = _review(sample[index], intent="other_unclear")
    result = score_audit({r.record_id: r.labels for r in sample}, reviews)
    assert (result.n, result.errors) == (540, 10)
    assert result.passed
    empty = score_audit({}, [])
    assert not empty.passed
    assert empty.n == 0


def test_review_errors_definition(audit_records: list[DatasetRecord]) -> None:
    record = audit_records[0]
    assert review_errors(record.labels, _review(record)) == []
    assert review_errors(
        record.labels, _review(record, customer_requested_human=True, entities_missing=True)
    ) == ["customer_requested_human", "entities"]


def test_second_annotation_sample(audit_records: list[DatasetRecord]) -> None:
    subset = second_annotation_sample(audit_records, fraction=0.2, seed=5)
    assert len(subset) == round(0.2 * len(audit_records))
    assert len({r.record_id for r in subset}) == len(subset)
    everything = second_annotation_sample(audit_records, fraction=1.0)
    assert {r.record_id for r in everything} == {r.record_id for r in audit_records}
