import hashlib
import json
import re
from enum import StrEnum

import pytest

from ticketward.domain.taxonomy import (
    CRITICAL_INTENTS,
    DEFAULT_ROUTING,
    FORCED_REVIEW_INTENTS,
    FRONTIER_DENYLIST,
    TAXONOMY_ENUMS,
    TAXONOMY_VERSION,
    ChurnRisk,
    DocType,
    EntityType,
    EscalationReason,
    Intent,
    PlanTier,
    Priority,
    ProductArea,
    Queue,
    RecommendedAction,
    RoutingDefault,
    Sentiment,
)
from ticketward.domain.taxonomy import Channel as TicketChannel
from ticketward.schemas.export import build_json_schemas

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

# Any change to a frozen enum changes this digest. If this test fails you edited the
# taxonomy: that requires an ADR, a new TAXONOMY_VERSION, relabeling and retraining
# (spec §5). Update the digest only as part of that change.
#
# History:
# - v1.0 (2026-09-26): a8781d0cdc16173f59b953aa8cddbc8c1757f54bfd428a7d703358b052ec0390
# - v1.1 (2026-09-27): deliberate update for spec v1.1 §5.9, which adds the system-emitted
#   reasons critical_category_suspected, queue_overridden_by_rule and pii_masking_failed
#   (ADR-0029 amendment). They are not model labels and nothing is labeled before the P1
#   freeze, so TAXONOMY_VERSION stays "2026-09-v1" (spec §5 v1.1 note).
FROZEN_FINGERPRINT = "1c8f1160e7b23fa0a2e5bd2f33f040e573f7305f44c9bcc10da72d809a0bb647"

# Spec v1.1 §5.9, copied independently of the implementation (order matters: it is the
# enum order exported to JSON Schema and TypeScript).
SPEC_ESCALATION_REASONS = [
    "customer_requested_human",
    "forced_category_refund",
    "forced_category_cancellation",
    "forced_category_payment_dispute",
    "forced_category_security",
    "forced_category_legal_threat",
    "forced_category_privacy",
    "active_incident",
    "critical_category_suspected",
    "low_confidence_intent",
    "low_confidence_queue",
    "queue_overridden_by_rule",
    "insufficient_evidence",
    "stale_evidence_only",
    "conflicting_evidence",
    "schema_invalid_after_repair",
    "prompt_injection_suspected",
    "unsupported_language",
    "high_churn_risk_high_value",
    "retention_risk",
    "pii_heavy_content",
    "pii_masking_failed",
    "input_truncated",
    "model_unavailable",
    "agent_initiated",
]


def taxonomy_fingerprint() -> str:
    document = {
        "version": TAXONOMY_VERSION,
        "enums": {enum.__name__: [member.value for member in enum] for enum in TAXONOMY_ENUMS},
    }
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()


def test_taxonomy_version() -> None:
    assert TAXONOMY_VERSION == "2026-09-v1"


def test_taxonomy_fingerprint_is_frozen() -> None:
    assert taxonomy_fingerprint() == FROZEN_FINGERPRINT


def test_escalation_reasons_match_spec_v1_1_list() -> None:
    assert [reason.value for reason in EscalationReason] == SPEC_ESCALATION_REASONS


@pytest.mark.parametrize(
    ("enum", "size"),
    [
        (Intent, 13),
        (Queue, 6),
        (Priority, 4),
        (Sentiment, 5),
        (ChurnRisk, 3),
        (ProductArea, 12),
        (EntityType, 21),
        (RecommendedAction, 17),
        (EscalationReason, 25),
        (PlanTier, 4),
        (TicketChannel, 4),
        (DocType, 6),
    ],
)
def test_enum_sizes_match_spec(enum: type[StrEnum], size: int) -> None:
    assert len(enum) == size


@pytest.mark.parametrize("enum", TAXONOMY_ENUMS, ids=lambda enum: enum.__name__)
def test_enum_values_are_snake_case_and_equal_member_names(enum: type[StrEnum]) -> None:
    for member in enum:
        assert SNAKE_CASE.fullmatch(member.value), member.value
        assert member.name == member.value


def test_every_intent_has_a_default_routing_entry() -> None:
    assert set(DEFAULT_ROUTING) == set(Intent)
    assert all(isinstance(entry, RoutingDefault) for entry in DEFAULT_ROUTING.values())


def test_default_routing_is_read_only() -> None:
    with pytest.raises(TypeError):
        DEFAULT_ROUTING[Intent.bug_report] = RoutingDefault(  # type: ignore[index]
            Queue.general_support_tier_1, RecommendedAction.no_action_spam
        )


# Spec §5.1 "Default queue" and §5.8, written out independently of the implementation.
SPEC_DEFAULT_ROUTING = {
    "sso_login_failure": (
        "technical_support_tier_2",
        "request_saml_error_details_and_check_known_incident",
    ),
    "account_access_issue": ("general_support_tier_1", "send_password_reset_guidance"),
    "billing_duplicate_charge": ("billing_and_accounts", "escalate_to_billing_for_review"),
    "billing_payment_failure": ("billing_and_accounts", "escalate_to_billing_for_review"),
    "refund_request": ("billing_and_accounts", "escalate_to_billing_for_review"),
    "cancellation_request": ("customer_success_retention", "escalate_to_csm_retention"),
    "plan_pricing_inquiry": ("general_support_tier_1", "share_pricing_page_reference"),
    "service_outage": ("incident_response", "check_known_incident_and_share_status"),
    "bug_report": ("technical_support_tier_2", "collect_repro_steps_and_escalate_to_engineering"),
    "how_to_question": ("general_support_tier_1", "answer_with_kb_article"),
    "security_report": ("security_and_privacy", "escalate_to_security"),
    "privacy_legal_request": ("security_and_privacy", "escalate_to_privacy_legal"),
    "other_unclear": ("general_support_tier_1", "request_more_information"),
}


def test_default_routing_matches_spec_table() -> None:
    actual = {
        intent.value: (entry.queue.value, entry.action.value)
        for intent, entry in DEFAULT_ROUTING.items()
    }
    assert actual == SPEC_DEFAULT_ROUTING


def test_every_queue_is_a_default_destination() -> None:
    assert {entry.queue for entry in DEFAULT_ROUTING.values()} == set(Queue)


def test_critical_intents_are_the_five_brief_categories() -> None:
    assert {intent.value for intent in CRITICAL_INTENTS} == {
        "security_report",
        "service_outage",
        "cancellation_request",
        "billing_duplicate_charge",
        "billing_payment_failure",
    }


def test_forced_review_intents_match_spec() -> None:
    assert {intent.value for intent in FORCED_REVIEW_INTENTS} == {
        "billing_duplicate_charge",
        "billing_payment_failure",
        "refund_request",
        "cancellation_request",
        "service_outage",
        "security_report",
        "privacy_legal_request",
    }


def test_every_critical_intent_is_forced_review() -> None:
    # Spec §5.1: all five critical categories are also forced-review; no exceptions.
    assert CRITICAL_INTENTS <= FORCED_REVIEW_INTENTS


def test_frontier_denylist_is_security_and_privacy() -> None:
    assert {Intent.security_report, Intent.privacy_legal_request} == FRONTIER_DENYLIST
    assert FRONTIER_DENYLIST <= FORCED_REVIEW_INTENTS


def test_other_unclear_is_neither_critical_nor_forced() -> None:
    assert Intent.other_unclear not in CRITICAL_INTENTS
    assert Intent.other_unclear not in FORCED_REVIEW_INTENTS
    assert (
        DEFAULT_ROUTING[Intent.other_unclear].action is RecommendedAction.request_more_information
    )


@pytest.mark.parametrize("enum", TAXONOMY_ENUMS, ids=lambda enum: enum.__name__)
def test_exported_taxonomy_schema_matches_python_enums(enum: type[StrEnum]) -> None:
    taxonomy = build_json_schemas()["taxonomy"]
    assert taxonomy["properties"]["taxonomy_version"] == {"const": TAXONOMY_VERSION}
    assert taxonomy["$defs"][enum.__name__]["enum"] == [member.value for member in enum]


def test_triage_output_schema_uses_the_same_enum_values() -> None:
    definitions = build_json_schemas()["triage_model_output"]["$defs"]
    for enum in (
        Intent,
        Queue,
        Priority,
        Sentiment,
        ChurnRisk,
        ProductArea,
        RecommendedAction,
        EntityType,
    ):
        assert definitions[enum.__name__]["enum"] == [member.value for member in enum]
