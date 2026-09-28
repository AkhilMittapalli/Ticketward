"""Spec §5.3 SLA targets with the §3 first-response multiplier (P1.5)."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from ticketward.domain.taxonomy import (
    BASE_SLA_TARGETS,
    PLAN_FRT_MULTIPLIER,
    SLA_BASE_PLAN,
    PlanTier,
    Priority,
    SlaDuration,
    SlaTargets,
    SlaUnit,
    sla_targets,
)

# Spec §5.3 "Base FRT" / "Base resolution target" (business plan) and the §3 "First-response
# SLA multiplier", copied independently of the implementation.
SPEC_BASE: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "urgent": (("1", "hours"), ("8", "hours")),
    "high": (("4", "hours"), ("1", "business_days")),
    "normal": (("1", "business_days"), ("3", "business_days")),
    "low": (("2", "business_days"), ("5", "business_days")),
}
SPEC_MULTIPLIER = {"free": "2", "starter": "1.5", "business": "1", "enterprise": "0.5"}
# First-response target = base x plan multiplier, in the base unit (worked out by hand).
EXPECTED_FRT: dict[str, dict[str, str]] = {
    "urgent": {"free": "2", "starter": "1.5", "business": "1", "enterprise": "0.5"},
    "high": {"free": "8", "starter": "6", "business": "4", "enterprise": "2"},
    "normal": {"free": "2", "starter": "1.5", "business": "1", "enterprise": "0.5"},
    "low": {"free": "4", "starter": "3", "business": "2", "enterprise": "1"},
}
PLANS_FASTEST_LAST = [PlanTier.free, PlanTier.starter, PlanTier.business, PlanTier.enterprise]


def _spec(amount: str, unit: str) -> SlaDuration:
    return SlaDuration(Decimal(amount), SlaUnit(unit))


def test_base_targets_match_spec() -> None:
    assert set(BASE_SLA_TARGETS) == set(Priority)
    for priority, (frt, resolution) in SPEC_BASE.items():
        assert BASE_SLA_TARGETS[Priority(priority)] == SlaTargets(_spec(*frt), _spec(*resolution))


def test_plan_multipliers_match_spec() -> None:
    assert {plan.value: value for plan, value in PLAN_FRT_MULTIPLIER.items()} == {
        plan: Decimal(value) for plan, value in SPEC_MULTIPLIER.items()
    }


def test_the_base_plan_is_business_with_multiplier_one() -> None:
    assert SLA_BASE_PLAN is PlanTier.business
    assert PLAN_FRT_MULTIPLIER[SLA_BASE_PLAN] == 1
    for priority in Priority:
        assert sla_targets(priority, SLA_BASE_PLAN) == BASE_SLA_TARGETS[priority]


@pytest.mark.parametrize("priority", list(Priority), ids=str)
@pytest.mark.parametrize("plan", list(PlanTier), ids=str)
def test_first_response_target_is_base_times_plan_multiplier(
    priority: Priority, plan: PlanTier
) -> None:
    targets = sla_targets(priority, plan)
    base = BASE_SLA_TARGETS[priority]
    assert targets.first_response == SlaDuration(
        Decimal(EXPECTED_FRT[priority][plan]), base.first_response.unit
    )
    # Spec-ambiguous point, decided conservatively: the multiplier is a first-response one.
    assert targets.resolution == base.resolution


def test_higher_tiers_get_faster_first_responses() -> None:
    multipliers = [PLAN_FRT_MULTIPLIER[plan] for plan in PLANS_FASTEST_LAST]
    assert multipliers == sorted(multipliers, reverse=True)
    assert len(set(multipliers)) == len(multipliers)


def test_enterprise_urgent_first_response_is_thirty_minutes() -> None:
    target = sla_targets(Priority.urgent, PlanTier.enterprise).first_response
    assert target == SlaDuration(Decimal("0.5"), SlaUnit.hours)
    assert target.amount * 60 == 30  # minutes


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity"])
def test_durations_must_be_positive_and_finite(amount: str) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        SlaDuration(Decimal(amount), SlaUnit.hours)


def test_scaling_keeps_the_unit_and_rejects_non_positive_factors() -> None:
    day = SlaDuration(Decimal(1), SlaUnit.business_days)
    assert day.scaled(Decimal("1.5")) == SlaDuration(Decimal("1.5"), SlaUnit.business_days)
    with pytest.raises(ValueError, match="positive and finite"):
        day.scaled(Decimal(0))


def test_sla_tables_are_read_only() -> None:
    with pytest.raises(TypeError):
        PLAN_FRT_MULTIPLIER[PlanTier.free] = Decimal(1)  # type: ignore[index]
    with pytest.raises(TypeError):
        BASE_SLA_TARGETS[Priority.low] = BASE_SLA_TARGETS[Priority.urgent]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        BASE_SLA_TARGETS[Priority.low].first_response = _spec("1", "hours")  # type: ignore[misc]
