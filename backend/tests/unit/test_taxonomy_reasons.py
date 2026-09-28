"""Spec §5.9 escalation reasons: one named emitter per reason, plus the forced reasons (P1.5)."""

import pytest

from ticketward.domain.taxonomy import (
    CRITICAL_INTENTS,
    EMITTER_BY_REASON,
    FORCED_REASONS,
    FORCED_REVIEW_INTENTS,
    FORCED_REVIEW_REASON,
    REASONS_BY_EMITTER,
    EscalationReason,
    Intent,
    ReasonEmitter,
    emitter_of,
    reasons_emitted_by,
)

# Spec §5.9 emitter table, copied independently of the implementation (one row per emitter).
SPEC_EMITTER_TABLE: dict[str, set[str]] = {
    "P0": {"prompt_injection_suspected"},
    "P1": {"customer_requested_human"},
    "P2": {"forced_category_security"},
    "P3": {"forced_category_privacy", "forced_category_legal_threat"},
    "P4": {"active_incident"},
    "P5": {
        "forced_category_refund",
        "forced_category_cancellation",
        "forced_category_payment_dispute",
    },
    "P6": {"unsupported_language"},
    "P7": {"pii_masking_failed", "model_unavailable", "schema_invalid_after_repair"},
    "P8": {"low_confidence_intent"},
    "P9": {"insufficient_evidence", "stale_evidence_only", "conflicting_evidence"},
    "N1": {"queue_overridden_by_rule", "low_confidence_queue"},
    "N2": {"high_churn_risk_high_value"},
    "N4": {"input_truncated"},
    "N5": {"pii_heavy_content"},
    "N6": {"critical_category_suspected"},
    "N7": {"retention_risk"},
    "escalations_api": {"agent_initiated"},  # POST /tickets/{id}/escalations (§11)
}
# Spec §7.3 rule ids. P10/P11 only choose a path and N3 only raises priority: no reasons.
SPEC_RULES = {f"P{n}" for n in range(12)} | {f"N{n}" for n in range(1, 8)}
RULES_WITHOUT_REASONS = {"P10", "P11", "N3"}
# Spec §7.3 P2-P5 "Effect" column; D6-6: duplicate charge and payment failure share one reason.
SPEC_FORCED_REVIEW_REASON = {
    "security_report": "forced_category_security",
    "privacy_legal_request": "forced_category_privacy",
    "service_outage": "active_incident",
    "refund_request": "forced_category_refund",
    "cancellation_request": "forced_category_cancellation",
    "billing_duplicate_charge": "forced_category_payment_dispute",
    "billing_payment_failure": "forced_category_payment_dispute",
}
FORCED_RULE_IDS = {"P1", "P2", "P3", "P4", "P5"}


def test_emitter_table_matches_spec() -> None:
    actual = {e.value: {r.value for r in reasons} for e, reasons in REASONS_BY_EMITTER.items()}
    assert actual == SPEC_EMITTER_TABLE


def test_the_spec_copy_lists_each_of_the_25_reasons_once() -> None:
    listed = [reason for reasons in SPEC_EMITTER_TABLE.values() for reason in reasons]
    assert len(listed) == len(set(listed)) == len(EscalationReason) == 25
    assert set(listed) == {reason.value for reason in EscalationReason}


@pytest.mark.parametrize("reason", list(EscalationReason), ids=str)
def test_every_reason_has_exactly_one_emitter_from_the_allowed_set(
    reason: EscalationReason,
) -> None:
    owners = [emitter for emitter, reasons in REASONS_BY_EMITTER.items() if reason in reasons]
    assert owners == [emitter_of(reason)]
    assert emitter_of(reason).value in SPEC_EMITTER_TABLE  # the allowed emitter set


def test_allowed_emitters_are_the_reason_emitting_rules_plus_the_endpoint() -> None:
    assert {emitter.value for emitter in ReasonEmitter} == set(SPEC_EMITTER_TABLE)
    assert set(SPEC_EMITTER_TABLE) == (SPEC_RULES - RULES_WITHOUT_REASONS) | {"escalations_api"}
    assert all(reasons_emitted_by(emitter) for emitter in ReasonEmitter)


def test_lookups_are_inverse() -> None:
    assert set(EMITTER_BY_REASON) == set(EscalationReason)
    for emitter in ReasonEmitter:
        for reason in reasons_emitted_by(emitter):
            assert emitter_of(reason) is emitter


def test_v1_1_system_reasons_have_their_named_emitters() -> None:
    # The three reasons added before the P1 freeze (ADR-0029 amendment).
    assert emitter_of(EscalationReason.queue_overridden_by_rule) is ReasonEmitter.N1
    assert emitter_of(EscalationReason.pii_masking_failed) is ReasonEmitter.P7
    assert emitter_of(EscalationReason.critical_category_suspected) is ReasonEmitter.N6


def test_only_the_escalation_endpoint_adds_agent_initiated() -> None:
    assert reasons_emitted_by(ReasonEmitter.escalations_api) == {EscalationReason.agent_initiated}


def test_forced_reasons_are_the_p1_to_p5_reasons() -> None:
    expected = {reason for rule in FORCED_RULE_IDS for reason in SPEC_EMITTER_TABLE[rule]}
    assert {reason.value for reason in FORCED_REASONS} == expected


def test_every_forced_review_intent_has_its_forced_reason() -> None:
    actual = {intent.value: reason.value for intent, reason in FORCED_REVIEW_REASON.items()}
    assert actual == SPEC_FORCED_REVIEW_REASON
    assert set(FORCED_REVIEW_REASON) == FORCED_REVIEW_INTENTS
    for reason in FORCED_REVIEW_REASON.values():
        assert reason in FORCED_REASONS
        assert emitter_of(reason).value in FORCED_RULE_IDS - {"P1"}


def test_every_critical_class_has_a_forced_reason() -> None:
    # Spec §9.12 D6-6: system-level critical recall counts "its forced reason".
    assert set(FORCED_REVIEW_REASON) >= CRITICAL_INTENTS
    shared = {
        intent
        for intent in CRITICAL_INTENTS
        if FORCED_REVIEW_REASON[intent] is EscalationReason.forced_category_payment_dispute
    }
    assert shared == {Intent.billing_duplicate_charge, Intent.billing_payment_failure}


def test_legal_threat_is_a_lexicon_only_forced_reason() -> None:
    assert EscalationReason.forced_category_legal_threat in FORCED_REASONS
    assert EscalationReason.forced_category_legal_threat not in set(FORCED_REVIEW_REASON.values())


def test_reason_tables_are_read_only() -> None:
    reason, emitter = EscalationReason.agent_initiated, ReasonEmitter.P1
    with pytest.raises(TypeError):
        EMITTER_BY_REASON[reason] = emitter  # type: ignore[index]
    with pytest.raises(TypeError):
        REASONS_BY_EMITTER[emitter] = frozenset()  # type: ignore[index]
    with pytest.raises(TypeError):
        FORCED_REVIEW_REASON[Intent.bug_report] = reason  # type: ignore[index]
    assert isinstance(reasons_emitted_by(emitter), frozenset)
