"""Property-based tests for the frozen policy tables (spec §5.3 N3 floors, §5.8, §5.9)."""

from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from ticketward.domain.taxonomy import (
    DEFAULT_ROUTING,
    EMITTER_BY_REASON,
    FORCED_REVIEW_INTENTS,
    PRIORITY_RANK,
    SELF_SERVE_ACTIONS,
    EscalationReason,
    Intent,
    PlanTier,
    Priority,
    PriorityFloorContext,
    ReasonEmitter,
    Sentiment,
    allowed_actions,
    allowed_queues,
    applicable_floors,
    apply_priority_floors,
    default_route,
    reasons_emitted_by,
)

INTENTS = st.sampled_from(Intent)
PRIORITIES = st.sampled_from(Priority)
CONTEXTS = st.builds(
    PriorityFloorContext,
    model_priority=PRIORITIES,
    intents=st.frozensets(INTENTS, min_size=1, max_size=3),  # a primary + at most 2 secondary
    plan=st.sampled_from(PlanTier),
    sentiment=st.sampled_from(Sentiment),
    suspension_language=st.booleans(),
    org_wide_cue=st.booleans(),
    user_count_affected=st.none() | st.integers(min_value=0, max_value=100_000),
)


def rank(priority: Priority) -> int:
    return PRIORITY_RANK[priority]


@given(CONTEXTS)
def test_floors_never_lower_a_priority(context: PriorityFloorContext) -> None:
    assert rank(apply_priority_floors(context)) >= rank(context.model_priority)


@given(CONTEXTS)
def test_final_priority_meets_every_floor_and_nothing_more(context: PriorityFloorContext) -> None:
    final = apply_priority_floors(context)
    floors = applicable_floors(context)
    assert all(rank(final) >= rank(floor) for floor in floors.values())
    # The result is the model's priority or one of the floors: N3 never invents a level.
    assert final is context.model_priority or final in floors.values()
    if not floors:
        assert final is context.model_priority


@given(CONTEXTS, PRIORITIES)
def test_a_higher_model_priority_never_gives_a_lower_result(
    context: PriorityFloorContext, other: Priority
) -> None:
    low, high = sorted((context.model_priority, other), key=rank)
    below = apply_priority_floors(replace(context, model_priority=low))
    above = apply_priority_floors(replace(context, model_priority=high))
    assert rank(below) <= rank(above)


@given(CONTEXTS, INTENTS)
def test_an_extra_intent_never_lowers_the_result(
    context: PriorityFloorContext, extra: Intent
) -> None:
    more = replace(context, intents=context.intents | {extra})
    assert rank(apply_priority_floors(more)) >= rank(apply_priority_floors(context))


@given(CONTEXTS)
def test_more_evidence_never_lowers_the_result(context: PriorityFloorContext) -> None:
    stronger = replace(
        context,
        suspension_language=True,
        org_wide_cue=True,
        plan=PlanTier.enterprise,
    )
    assert rank(apply_priority_floors(stronger)) >= rank(apply_priority_floors(context))


@given(INTENTS)
def test_every_intent_has_a_default_route_inside_its_allow_list(intent: Intent) -> None:
    route = default_route(intent)
    assert route is DEFAULT_ROUTING[intent]
    assert route.queue in allowed_queues(intent)
    assert route.action in allowed_actions(intent)


@given(st.sampled_from(sorted(FORCED_REVIEW_INTENTS)))
def test_forced_review_intents_never_allow_self_service(intent: Intent) -> None:
    assert allowed_actions(intent).isdisjoint(SELF_SERVE_ACTIONS)


@given(st.sampled_from(EscalationReason))
def test_every_reason_has_exactly_one_emitter(reason: EscalationReason) -> None:
    owners = [emitter for emitter in ReasonEmitter if reason in reasons_emitted_by(emitter)]
    assert owners == [EMITTER_BY_REASON[reason]]
