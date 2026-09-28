"""Spec §5.3 rule-N3 priority floors, table-driven from the spec text (P1.5)."""

from typing import NamedTuple

import pytest

from ticketward.domain.taxonomy import (
    NEGATIVE_SENTIMENTS,
    ORG_WIDE_MIN_USERS_AFFECTED,
    PRIORITY_RANK,
    Intent,
    PlanTier,
    Priority,
    PriorityFloorContext,
    PriorityFloorRule,
    Sentiment,
    applicable_floors,
    apply_priority_floors,
    max_priority,
    priority_floor,
    raise_priority,
)

ENT, BIZ = PlanTier.enterprise, PlanTier.business
ANGRY, FRUSTRATED = Sentiment.angry, Sentiment.frustrated
F = PriorityFloorRule
HIGH, URGENT, NORMAL, LOW = Priority.high, Priority.urgent, Priority.normal, Priority.low


def ctx(
    *intents: Intent,
    model: Priority = NORMAL,
    plan: PlanTier = BIZ,
    sentiment: Sentiment = Sentiment.neutral,
    suspension: bool = False,
    org_wide_cue: bool = False,
    users: int | None = None,
) -> PriorityFloorContext:
    return PriorityFloorContext(
        model_priority=model,
        intents=frozenset(intents),
        plan=plan,
        sentiment=sentiment,
        suspension_language=suspension,
        org_wide_cue=org_wide_cue,
        user_count_affected=users,
    )


class Case(NamedTuple):
    context: PriorityFloorContext
    final: Priority
    floors: dict[PriorityFloorRule, Priority]


SSO, SECURITY, OUTAGE = Intent.sso_login_failure, Intent.security_report, Intent.service_outage
PAYMENT, BUG = Intent.billing_payment_failure, Intent.bug_report

# Every clause of the §5.3 floor sentence, its boundaries, and the spec's demo case 1.
CASES: dict[str, Case] = {
    "security floors normal at high": Case(ctx(SECURITY), HIGH, {F.security_report: HIGH}),
    "security raises low": Case(ctx(SECURITY, model=LOW), HIGH, {F.security_report: HIGH}),
    "security keeps urgent": Case(ctx(SECURITY, model=URGENT), URGENT, {F.security_report: HIGH}),
    "outage is urgent": Case(ctx(OUTAGE, model=LOW), URGENT, {F.service_outage: URGENT}),
    "secondary outage": Case(ctx(BUG, OUTAGE), URGENT, {F.service_outage: URGENT}),
    "payment failure + suspension": Case(
        ctx(PAYMENT, suspension=True), HIGH, {F.payment_failure_suspension: HIGH}
    ),
    "payment failure alone": Case(ctx(PAYMENT), NORMAL, {}),
    "suspension, no payment failure": Case(ctx(Intent.refund_request, suspension=True), NORMAL, {}),
    "enterprise SSO, org-wide cue": Case(
        ctx(SSO, model=HIGH, plan=ENT, org_wide_cue=True),
        URGENT,
        {F.enterprise_org_wide_sso: URGENT},
    ),
    "enterprise SSO, 10 users": Case(
        ctx(SSO, plan=ENT, users=10), URGENT, {F.enterprise_org_wide_sso: URGENT}
    ),
    "enterprise SSO, 9 users": Case(ctx(SSO, plan=ENT, users=9), NORMAL, {}),
    "enterprise SSO, no org-wide evidence": Case(ctx(SSO, plan=ENT), NORMAL, {}),
    "demo case 1 (business, frustrated)": Case(
        ctx(SSO, model=HIGH, sentiment=FRUSTRATED, org_wide_cue=True), HIGH, {}
    ),
    "org-wide cue without SSO": Case(ctx(BUG, plan=ENT, org_wide_cue=True, users=500), NORMAL, {}),
    "enterprise frustrated low": Case(
        ctx(Intent.how_to_question, model=LOW, plan=ENT, sentiment=FRUSTRATED),
        NORMAL,
        {F.enterprise_negative_sentiment: NORMAL},
    ),
    "enterprise angry high": Case(
        ctx(BUG, model=HIGH, plan=ENT, sentiment=ANGRY),
        URGENT,
        {F.enterprise_negative_sentiment: URGENT},
    ),
    "enterprise angry urgent stays": Case(
        ctx(BUG, model=URGENT, plan=ENT, sentiment=ANGRY),
        URGENT,
        {F.enterprise_negative_sentiment: URGENT},
    ),
    "enterprise confused": Case(ctx(BUG, plan=ENT, sentiment=Sentiment.confused), NORMAL, {}),
    "starter angry": Case(ctx(BUG, plan=PlanTier.starter, sentiment=ANGRY), NORMAL, {}),
    "maximum, never chained": Case(
        ctx(SECURITY, model=LOW, plan=ENT, sentiment=ANGRY),
        HIGH,
        {F.security_report: HIGH, F.enterprise_negative_sentiment: NORMAL},
    ),
    "security + enterprise angry from high": Case(
        ctx(SECURITY, model=HIGH, plan=ENT, sentiment=ANGRY),
        URGENT,
        {F.security_report: HIGH, F.enterprise_negative_sentiment: URGENT},
    ),
    "every floor at once": Case(
        ctx(
            SECURITY,
            OUTAGE,
            PAYMENT,
            SSO,
            model=LOW,
            plan=ENT,
            sentiment=ANGRY,
            suspension=True,
            org_wide_cue=True,
        ),
        URGENT,
        {
            F.security_report: HIGH,
            F.service_outage: URGENT,
            F.payment_failure_suspension: HIGH,
            F.enterprise_org_wide_sso: URGENT,
            F.enterprise_negative_sentiment: NORMAL,
        },
    ),
}


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_n3_floor_cases(case: Case) -> None:
    fired = applicable_floors(case.context)
    assert list(fired.items()) == list(case.floors.items())  # spec order, exact minimums
    assert apply_priority_floors(case.context) is case.final
    assert priority_floor(case.context) == (max_priority(*fired.values()) if fired else None)


def test_floors_follow_the_spec_order() -> None:
    assert [rule.value for rule in PriorityFloorRule] == [
        "security_report",
        "service_outage",
        "payment_failure_suspension",
        "enterprise_org_wide_sso",
        "enterprise_negative_sentiment",
    ]


def test_the_floor_is_applied_once_because_the_sentiment_floor_is_relative() -> None:
    first = apply_priority_floors(ctx(BUG, plan=ENT, sentiment=ANGRY))
    again = apply_priority_floors(ctx(BUG, model=first, plan=ENT, sentiment=ANGRY))
    assert (first, again) == (HIGH, URGENT)


def test_no_floor_leaves_the_priority_alone() -> None:
    context = ctx(Intent.how_to_question, model=LOW, plan=ENT)
    assert applicable_floors(context) == {}
    assert priority_floor(context) is None
    assert apply_priority_floors(context) is LOW


def test_floor_constants_match_spec() -> None:
    assert ORG_WIDE_MIN_USERS_AFFECTED == 10  # "user_count_affected >= 10" (§5.3, A-29)
    assert {Sentiment.frustrated, Sentiment.angry} == NEGATIVE_SENTIMENTS


def test_priority_rank_follows_the_enum_order() -> None:
    # The Priority enum lists the most urgent first; ranks grow with urgency.
    ranks = [PRIORITY_RANK[priority] for priority in Priority]
    assert ranks == [3, 2, 1, 0]


@pytest.mark.parametrize(
    ("start", "levels", "expected"),
    [
        (LOW, 1, NORMAL),
        (NORMAL, 1, HIGH),
        (HIGH, 1, URGENT),
        (URGENT, 1, URGENT),
        (LOW, 0, LOW),
        (LOW, 2, HIGH),
        (LOW, 10, URGENT),
    ],
)
def test_raise_priority_caps_at_urgent(start: Priority, levels: int, expected: Priority) -> None:
    assert raise_priority(start, levels) is expected


def test_raise_priority_never_lowers() -> None:
    with pytest.raises(ValueError, match="levels must be >= 0"):
        raise_priority(HIGH, -1)


def test_max_priority() -> None:
    assert max_priority(LOW) is LOW
    assert max_priority(NORMAL, URGENT, HIGH) is URGENT


@pytest.mark.parametrize(
    ("cue", "users", "expected"),
    [
        (True, None, True),
        (False, 10, True),
        (False, 11, True),
        (False, 9, False),
        (False, None, False),
    ],
)
def test_org_wide_is_a_cue_or_ten_users(cue: bool, users: int | None, expected: bool) -> None:
    assert ctx(SSO, org_wide_cue=cue, users=users).org_wide is expected


def test_context_requires_an_intent_and_a_valid_count() -> None:
    with pytest.raises(ValueError, match="at least the primary intent"):
        ctx()
    with pytest.raises(ValueError, match="user_count_affected must be >= 0"):
        ctx(SSO, users=-1)


def test_fired_floors_are_read_only() -> None:
    fired = applicable_floors(ctx(SECURITY))
    with pytest.raises(TypeError):
        fired[F.service_outage] = URGENT  # type: ignore[index]
