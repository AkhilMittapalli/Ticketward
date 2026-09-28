"""tw_ml.eval.metrics: every metric checked against hand-computed answers on tiny sets."""

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from sklearn.metrics import f1_score

from tw_ml.datagen.labelrules import LabelRules, load_label_rules
from tw_ml.datagen.records import TriageLabels
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy
from tw_ml.eval.data import (
    EvalSet,
    GoldItem,
    PolicyDecision,
    PolicyOutcome,
    PredictionRecord,
    join,
)
from tw_ml.eval.metrics import (
    INVALID,
    EvalSettings,
    MetricSuite,
    caught_by_system,
    compare_systems,
    entity_counts,
    evaluate,
    is_forced,
    macro_intents,
    seed_mean_macro_f1,
)

SETTINGS = EvalSettings(n_resamples=400, seed=7)
Ents = Sequence[tuple[str, str]]
# id, gold intent, pred intent, gold/pred priority, gold/pred sentiment, gold/pred churn,
# gold/pred product area, gold/pred entities, validity (None = no prediction at all)
ROWS: list[tuple[Any, ...]] = [
    (
        "va_001",
        "sso_login_failure",
        "sso_login_failure",
        "high",
        "high",
        "neutral",
        "neutral",
        "low",
        "low",
        "projects_tasks",
        "projects_tasks",
        [("error_code", "SAML_ERR_302"), ("saml_idp", "okta")],
        [("error_code", "SAML_ERR_302"), ("saml_idp", "okta")],
        "first_pass",
    ),
    (
        "va_002",
        "sso_login_failure",
        "account_access_issue",
        "high",
        "normal",
        "neutral",
        "neutral",
        "low",
        "low",
        "projects_tasks",
        "sso_identity",
        [("error_code", "SAML_ERR_401")],
        [("error_code", "SAML_ERR_401"), ("http_status", "HTTP 503")],
        "repaired_l1",
    ),
    (
        "va_003",
        "security_report",
        "security_report",
        "urgent",
        "low",
        "angry",
        "angry",
        "low",
        "medium",
        "projects_tasks",
        "projects_tasks",
        [],
        [],
        "first_pass",
    ),
    (
        "va_004",
        "security_report",
        "how_to_question",
        "high",
        "urgent",
        "angry",
        "frustrated",
        "medium",
        "medium",
        "projects_tasks",
        "sso_identity",
        [("feature_name", "Audit log")],
        [],
        "repaired_l2",
    ),
    (
        "va_005",
        "how_to_question",
        "how_to_question",
        "low",
        "low",
        "neutral",
        "neutral",
        "low",
        "low",
        "projects_tasks",
        "projects_tasks",
        [],
        [("feature_name", "Dashboards")],
        "first_pass",
    ),
    (
        "va_006",
        "other_unclear",
        "how_to_question",
        "low",
        "normal",
        "confused",
        "neutral",
        "low",
        "low",
        "projects_tasks",
        "projects_tasks",
        [],
        [],
        "first_pass",
    ),
    (
        "va_007",
        "cancellation_request",
        "cancellation_request",
        "normal",
        "normal",
        "frustrated",
        "frustrated",
        "high",
        "high",
        "projects_tasks",
        "projects_tasks",
        [("workspace_id", "ws_0000abcd")],
        [("workspace_id", "ws_0000ABCD")],
        "failed_fallback",
    ),
    (
        "va_008",
        "bug_report",
        None,
        "normal",
        None,
        "neutral",
        None,
        "low",
        None,
        "projects_tasks",
        None,
        [("error_code", "IMP_ERR_ROWS")],
        None,
        None,
    ),
]

Labeler = Callable[..., TriageLabels]


@pytest.fixture(scope="module")
def tax() -> Taxonomy:
    return load_taxonomy()


@pytest.fixture(scope="module")
def lrules(tax: Taxonomy) -> LabelRules:
    return load_label_rules(taxonomy=tax)


@pytest.fixture
def labeler(make_labels: Callable[..., TriageLabels], lrules: LabelRules) -> Labeler:
    def build(intent: str, *, entities: Ents = (), **overrides: Any) -> TriageLabels:
        values: dict[str, Any] = {
            "intent": intent,
            "entities": [{"type": t, "value": v} for t, v in entities],
            "recommended_queue": lrules.routing[intent].queue,
            "recommended_action": lrules.routing[intent].action,
        }
        values.update(overrides)
        return make_labels(**values)

    return build


@pytest.fixture
def classification_set(labeler: Labeler) -> EvalSet:
    gold, predictions = [], []
    for row in ROWS:
        rid, gi, pi, gp, pp, gs, ps, gc, pc, ga, pa, ge, pe, validity = row
        gold.append(
            GoldItem(
                rid,
                labeler(gi, priority=gp, sentiment=gs, churn_risk=gc, product_area=ga, entities=ge),
            )
        )
        if validity is not None:
            output = labeler(
                pi, priority=pp, sentiment=ps, churn_risk=pc, product_area=pa, entities=pe
            )
            predictions.append(
                PredictionRecord(record_id=rid, system_id="sys-a", validity=validity, output=output)
            )
    return join(gold, predictions)


@pytest.fixture
def suite(classification_set: EvalSet, tax: Taxonomy, lrules: LabelRules) -> MetricSuite:
    return evaluate(classification_set, tax, lrules, SETTINGS)


def _point(suite: MetricSuite, metric_id: str) -> float | None:
    return suite.metrics[metric_id].estimate.point


# --------------------------------------------------------------------------- M-01


def test_intent_macro_f1_hand_computed(suite: MetricSuite, tax: Taxonomy) -> None:
    # Per-class F1 over the 12: sso 2/3, account 0, security 2/3, how_to 1/2, cancellation 1,
    # bug 0 (missing prediction), six absent classes 0 -> 17/6 / 12 = 17/72.
    assert _point(suite, "M-01.intent_macro_f1") == pytest.approx(17 / 72)
    gold = [row[1] for row in ROWS]
    pred = [row[2] or INVALID for row in ROWS]
    sklearn_value = f1_score(
        gold, pred, labels=list(macro_intents(tax)), average="macro", zero_division=0
    )
    assert _point(suite, "M-01.intent_macro_f1") == pytest.approx(sklearn_value)
    macro = suite.metrics["M-01.intent_macro_f1"]
    assert macro.estimate.method == "stratified-percentile-bootstrap"
    assert (macro.estimate.n, macro.estimate.n_resamples, macro.estimate.rng_seed) == (8, 400, 7)
    assert "billing_duplicate_charge" in macro.notes  # absent classes are named


def test_intent_accuracy_and_other_unclear(suite: MetricSuite) -> None:
    accuracy = suite.metrics["M-01.intent_accuracy"].estimate
    assert (accuracy.point, accuracy.k, accuracy.n, accuracy.method) == (0.5, 4, 8, "wilson")
    assert _point(suite, "M-01.other_unclear_f1") == 0.0
    recall = suite.metrics["M-01.other_unclear_recall"].estimate
    assert (recall.point, recall.n, recall.method) == (0.0, 1, "clopper-pearson")
    assert suite.metrics["M-01.other_unclear_precision"].estimate.point is None  # never predicted


def test_per_class_rows_and_confusion(suite: MetricSuite) -> None:
    rows = {row.label: row for row in suite.per_class["intent"]}
    sso = rows["sso_login_failure"]
    assert (sso.support, sso.predicted, sso.tp, sso.precision, sso.recall) == (2, 1, 1, 1.0, 0.5)
    assert sso.f1 == pytest.approx(2 / 3)
    how_to = rows["how_to_question"]
    assert (how_to.support, how_to.predicted, how_to.f1) == (1, 3, 0.5)
    assert rows["refund_request"].f1 is None  # absent: undefined in the table, 0 in the macro
    matrix = suite.confusion["intent"]
    assert matrix.predicted_labels[-1] == INVALID
    bug = matrix.gold_labels.index("bug_report")
    assert matrix.counts[bug][-1] == 1
    assert sum(map(sum, matrix.counts)) == 8


# --------------------------------------------------------------------------- M-02 .. M-04


def test_routing_accuracy_uses_the_model_queue_without_decisions(suite: MetricSuite) -> None:
    routing = suite.metrics["M-02.routing_accuracy"]
    assert (routing.estimate.k, routing.estimate.n) == (5, 8)
    assert "model queue for 7" in routing.notes


def test_field_metrics_hand_computed(suite: MetricSuite) -> None:
    assert _point(suite, "M-03.priority_accuracy") == pytest.approx(3 / 8)
    assert _point(suite, "M-03.priority_within_one") == pytest.approx(6 / 8)
    assert _point(suite, "M-03.product_area_accuracy") == pytest.approx(5 / 8)
    # sentiment: neutral 3/4, frustrated 2/3, angry 2/3, positive 0, confused 0 -> 5/12
    assert _point(suite, "M-03.sentiment_macro_f1") == pytest.approx(5 / 12)
    # churn: low 4/5, medium 2/3, high 1 -> 37/45
    assert _point(suite, "M-03.churn_macro_f1") == pytest.approx(37 / 45)


def test_entity_f1_exact_type_and_value(suite: MetricSuite) -> None:
    # tp 3 (va_001 x2, va_002), fp 3 (HTTP 503, Dashboards, case-changed ws id), fn 3
    for metric_id in ("M-03.entity_f1", "M-03.entity_precision", "M-03.entity_recall"):
        assert _point(suite, metric_id) == pytest.approx(0.5)
    f1 = suite.metrics["M-03.entity_f1"]
    assert f1.estimate.method == "ticket-cluster-percentile-bootstrap"
    assert "gold entities 6, predicted 6, matched 3" in f1.notes


def test_entity_counts_is_a_multiset_match(labeler: Labeler) -> None:
    gold = labeler(
        "bug_report", entities=[("error_code", "A_ERR_1"), ("error_code", "A_ERR_1")]
    ).entities
    pred = labeler(
        "bug_report", entities=[("error_code", "A_ERR_1"), ("http_status", "A_ERR_1")]
    ).entities
    assert entity_counts(gold, pred) == (1, 1, 1)
    spaced = labeler("bug_report", entities=[("error_code", " A_ERR_1 ")]).entities
    assert entity_counts(gold[:1], spaced) == (1, 0, 0)  # NFKC + trim, never case-folded


def test_critical_recall_model_level(suite: MetricSuite) -> None:
    rows = {row.label: row for row in suite.per_class["critical_model"]}
    assert set(rows) == {
        "billing_duplicate_charge",
        "billing_payment_failure",
        "cancellation_request",
        "service_outage",
        "security_report",
    }
    assert (rows["security_report"].tp, rows["security_report"].support) == (1, 2)
    pooled = suite.metrics["M-03c.model.pooled_recall"].estimate
    assert (pooled.k, pooled.n) == (2, 3)
    assert suite.metrics["M-03c.model.service_outage_recall"].estimate.point is None
    assert "critical_system" not in suite.per_class  # no policy decisions in this set


def test_validity_tiers(suite: MetricSuite) -> None:
    assert suite.validity_counts == {
        "first_pass": 4,
        "repaired_l1": 1,
        "repaired_l2": 1,
        "failed_fallback": 1,
        "missing": 1,
    }
    assert _point(suite, "M-04.json_validity") == pytest.approx(6 / 8)
    assert _point(suite, "M-04.first_pass") == pytest.approx(4 / 8)
    assert _point(suite, "M-04.schema_repair") == pytest.approx(2 / 8)
    assert _point(suite, "M-04.failed") == pytest.approx(2 / 8)


def test_suite_notes_and_no_m07_without_decisions(suite: MetricSuite) -> None:
    assert not suite.decision_level
    assert "M-07a.forced_escalation" not in suite.metrics
    assert any("M-07a..d not computed" in note for note in suite.notes)
    assert any("1 gold records have no prediction" in note for note in suite.notes)


# --------------------------------------------------------------------------- M-07 (decisions)


def _decision(path: PolicyDecision, *reasons: str, queue: str | None = None) -> PolicyOutcome:
    return PolicyOutcome(
        policy_decision=path,
        needs_human_review=path == "human_escalation",
        escalation_reasons=reasons,
        final_queue=queue,
    )


@pytest.fixture
def decision_set(labeler: Labeler) -> EvalSet:
    human = {"customer_requested_human": True, "recommended_action": "offer_human_contact"}
    cases: list[tuple[str, GoldItem, PolicyOutcome | None, str]] = [
        (
            "va_101",
            GoldItem("va_101", labeler("refund_request")),
            _decision("human_escalation", "forced_category_refund"),
            "refund_request",
        ),
        (
            "va_102",
            GoldItem("va_102", labeler("security_report")),
            _decision("local_draft"),
            "security_report",
        ),  # a policy miss the model would catch
        (
            "va_103",
            GoldItem("va_103", labeler("how_to_question")),
            _decision("local_draft"),
            "how_to_question",
        ),
        (
            "va_104",
            GoldItem("va_104", labeler("how_to_question")),
            _decision("human_escalation", "insufficient_evidence"),
            "how_to_question",
        ),
        (
            "va_105",
            GoldItem("va_105", labeler("how_to_question", **human), human_request_kind="direct"),
            _decision("human_escalation", "customer_requested_human"),
            "how_to_question",
        ),
        (
            "va_106",
            GoldItem("va_106", labeler("other_unclear", information_sufficient=False)),
            _decision("abstain_request_info"),
            "other_unclear",
        ),
        (
            "va_107",
            GoldItem("va_107", labeler("bug_report", **human), human_request_kind="indirect"),
            _decision("local_draft"),
            "bug_report",
        ),
        ("va_108", GoldItem("va_108", labeler("billing_duplicate_charge")), None, ""),
    ]
    predictions = [
        PredictionRecord(record_id=rid, system_id="e5", output=labeler(intent), decision=decision)
        for rid, _, decision, intent in cases
        if decision is not None
    ]
    return join([gold for _, gold, _, _ in cases], predictions)


@pytest.fixture
def decision_suite(decision_set: EvalSet, tax: Taxonomy, lrules: LabelRules) -> MetricSuite:
    return evaluate(decision_set, tax, lrules, SETTINGS)


def test_m07a_forced_escalation_with_exact_lower_bound(decision_suite: MetricSuite) -> None:
    m07a = decision_suite.metrics["M-07a.forced_escalation"]
    assert (m07a.estimate.k, m07a.estimate.n) == (
        1,
        3,
    )  # refund escalated; security, duplicate missed
    assert m07a.lower_bound_one_sided == pytest.approx(1 - 0.95 ** (1 / 3))
    assert "1 items without a decision count as misses" in m07a.notes


def test_m07b_c_d(decision_suite: MetricSuite) -> None:
    metrics = decision_suite.metrics
    assert (
        metrics["M-07b.correct_abstention"].estimate.k,
        metrics["M-07b.correct_abstention"].estimate.n,
    ) == (1, 1)
    assert (
        metrics["M-07c.over_escalation"].estimate.k,
        metrics["M-07c.over_escalation"].estimate.n,
    ) == (1, 2)
    explicit = metrics["M-07d.human_request_recall_explicit"].estimate
    indirect = metrics["M-07d.human_request_recall_indirect"].estimate
    pooled = metrics["M-07d.human_request_recall"].estimate
    assert (explicit.k, explicit.n, indirect.k, indirect.n, pooled.k, pooled.n) == (
        1,
        1,
        0,
        1,
        1,
        2,
    )
    fpr = metrics["M-07d.false_positive_rate"].estimate
    assert (fpr.k, fpr.n) == (0, 6)


def test_system_level_critical_recall(decision_suite: MetricSuite, decision_set: EvalSet) -> None:
    rows = {row.label: row for row in decision_suite.per_class["critical_system"]}
    assert (rows["security_report"].tp, rows["security_report"].support) == (1, 1)
    assert (rows["billing_duplicate_charge"].tp, rows["billing_duplicate_charge"].support) == (0, 1)
    pooled = decision_suite.metrics["M-03c.system.pooled_recall"].estimate
    assert (pooled.k, pooled.n) == (1, 2)
    refund = next(i for i in decision_set.items if i.record_id == "va_101")
    assert not caught_by_system(refund, "billing_duplicate_charge")


def test_caught_by_reason_and_n6(labeler: Labeler) -> None:
    gold = GoldItem("va_1", labeler("service_outage"))
    for decision, expected in (
        (_decision("human_escalation", "active_incident"), True),
        (_decision("human_escalation", "critical_category_suspected"), True),
        (_decision("local_draft", "critical_category_suspected"), False),  # N6 without review
        (_decision("local_draft"), False),
    ):
        item = join(
            [gold],
            [
                PredictionRecord(
                    record_id="va_1", system_id="s", output=labeler("bug_report"), decision=decision
                )
            ],
        ).items[0]
        assert caught_by_system(item, "service_outage") is expected


def test_is_forced_covers_legal_threats_and_gold_reasons(
    labeler: Labeler, lrules: LabelRules
) -> None:
    assert not is_forced(GoldItem("va_1", labeler("bug_report")), lrules)
    assert is_forced(GoldItem("va_1", labeler("bug_report"), legal_threat=True), lrules)
    assert is_forced(
        GoldItem("va_1", labeler("bug_report", secondary_intents=["refund_request"])), lrules
    )


# --------------------------------------------------------------------------- comparisons, seeds


def test_compare_systems_paired_protocol(
    classification_set: EvalSet, labeler: Labeler, tax: Taxonomy
) -> None:
    gold = [item.gold for item in classification_set.items]
    perfect = [
        PredictionRecord(record_id=g.record_id, system_id="oracle", output=g.labels) for g in gold
    ]
    oracle = join(gold, perfect)
    result = compare_systems(oracle, classification_set, tax, SETTINGS, alternative="greater")
    assert result.macro_f1_a is not None
    assert result.macro_f1_b is not None
    assert result.delta_macro_f1.point == pytest.approx(result.macro_f1_a - result.macro_f1_b)
    assert result.macro_f1_b == pytest.approx(17 / 72)
    assert result.delta_accuracy.point == pytest.approx(0.5)
    assert (result.mcnemar.n10, result.mcnemar.n01) == (4, 0)
    assert 0 < result.p_randomization <= 1
    assert result.system_a == "oracle"
    with pytest.raises(ValueError, match="same gold records"):
        compare_systems(join(gold[:3], perfect), classification_set, tax, SETTINGS)


def test_seed_mean_macro_f1(classification_set: EvalSet, tax: Taxonomy) -> None:
    interval = seed_mean_macro_f1([classification_set, classification_set], tax, SETTINGS)
    assert interval.point == pytest.approx(17 / 72)
    assert interval.method == "stratified-two-level-percentile-bootstrap"


def test_empty_gold_set(tax: Taxonomy, lrules: LabelRules) -> None:
    empty = evaluate(join([], []), tax, lrules, SETTINGS)
    assert empty.n_items == 0
    assert empty.metrics == {}
    assert "undefined" in empty.notes[0]
