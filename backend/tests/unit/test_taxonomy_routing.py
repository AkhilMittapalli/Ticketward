"""Spec §5.8 routing: defaults, override allow-lists and the self-service guard (P1.5)."""

from dataclasses import FrozenInstanceError

import pytest

from ticketward.domain.taxonomy import (
    DEFAULT_ROUTING,
    FORCED_REVIEW_INTENTS,
    HUMAN_REQUEST_ACTION,
    ROUTING_OVERRIDES,
    SELF_SERVE_ACTIONS,
    Intent,
    Queue,
    RecommendedAction,
    RoutingOverrides,
    allowed_actions,
    allowed_overrides,
    allowed_queues,
    default_route,
)

# Written out independently of the implementation. Spec §5.8 names one alternate queue
# (sso_login_failure -> {tier_2, incident_response}); every other intent has none (spec-silent,
# conservative). The one alternate action is derived: spam is other_unclear (§5.1) and
# no_action_spam is the spam action (§5.7, labeling guideline R13).
SPEC_ALTERNATE_QUEUES: dict[str, set[str]] = {"sso_login_failure": {"incident_response"}}
SPEC_ALTERNATE_ACTIONS: dict[str, set[str]] = {"other_unclear": {"no_action_spam"}}
SPEC_SELF_SERVE_ACTIONS = {
    "answer_with_kb_article",
    "share_pricing_page_reference",
    "send_password_reset_guidance",
    "no_action_spam",
    "close_as_duplicate_ticket",
}
ALL_INTENTS = list(Intent)
FORCED = sorted(FORCED_REVIEW_INTENTS)


def test_every_intent_has_a_default_route_and_an_override_entry() -> None:
    for intent in Intent:
        assert default_route(intent) is DEFAULT_ROUTING[intent]
    assert set(ROUTING_OVERRIDES) == set(Intent)
    assert all(isinstance(entry, RoutingOverrides) for entry in ROUTING_OVERRIDES.values())


@pytest.mark.parametrize("intent", ALL_INTENTS, ids=str)
def test_alternates_match_the_spec(intent: Intent) -> None:
    overrides = allowed_overrides(intent)
    assert {queue.value for queue in overrides.queues} == SPEC_ALTERNATE_QUEUES.get(intent, set())
    assert {action.value for action in overrides.actions} == SPEC_ALTERNATE_ACTIONS.get(
        intent, set()
    )


def test_sso_allow_list_is_the_spec_example() -> None:
    # Spec §5.8: "sso_login_failure -> {tier_2, incident_response}".
    assert allowed_queues(Intent.sso_login_failure) == {
        Queue.technical_support_tier_2,
        Queue.incident_response,
    }


@pytest.mark.parametrize("intent", ALL_INTENTS, ids=str)
def test_allowed_sets_are_the_default_plus_alternates(intent: Intent) -> None:
    default, overrides = default_route(intent), allowed_overrides(intent)
    assert default.queue not in overrides.queues
    assert default.action not in overrides.actions
    assert allowed_queues(intent) == {default.queue} | overrides.queues
    assert allowed_actions(intent) == {default.action} | overrides.actions


@pytest.mark.parametrize("intent", ALL_INTENTS, ids=str)
@pytest.mark.parametrize("queue", list(Queue), ids=str)
def test_n1_keeps_only_the_default_or_a_listed_alternate(intent: Intent, queue: Queue) -> None:
    expected = queue is DEFAULT_ROUTING[intent].queue or queue in SPEC_ALTERNATE_QUEUES.get(
        intent, set()
    )
    assert (queue in allowed_queues(intent)) is expected


@pytest.mark.parametrize("intent", FORCED, ids=str)
def test_forced_review_intents_never_allow_a_self_serve_action(intent: Intent) -> None:
    assert allowed_overrides(intent).actions.isdisjoint(SELF_SERVE_ACTIONS)
    assert allowed_actions(intent).isdisjoint(SELF_SERVE_ACTIONS)  # the default included


@pytest.mark.parametrize("intent", FORCED, ids=str)
def test_forced_review_intents_keep_their_default_route(intent: Intent) -> None:
    # Conservative v1 choice: the model never moves a forced-review ticket off its default;
    # the §7.3.2 forced-queue rows still apply on top.
    assert allowed_overrides(intent) == RoutingOverrides()


def test_self_serve_actions() -> None:
    assert {action.value for action in SELF_SERVE_ACTIONS} == SPEC_SELF_SERVE_ACTIONS
    assert HUMAN_REQUEST_ACTION not in SELF_SERVE_ACTIONS
    assert RecommendedAction.request_more_information not in SELF_SERVE_ACTIONS


def test_p1_sets_offer_human_contact() -> None:
    # Spec §7.3 P1: "action offer_human_contact" (S-02).
    assert HUMAN_REQUEST_ACTION is RecommendedAction.offer_human_contact


def test_allow_lists_are_read_only() -> None:
    with pytest.raises(TypeError):
        ROUTING_OVERRIDES[Intent.bug_report] = RoutingOverrides()  # type: ignore[index]
    entry = allowed_overrides(Intent.sso_login_failure)
    assert isinstance(entry.queues, frozenset)
    assert isinstance(entry.actions, frozenset)
    with pytest.raises(FrozenInstanceError):
        entry.queues = frozenset()  # type: ignore[misc]
