"""Tests for the P1.6 contracts: DraftResponse, TemplateReply, handoff variants, FeedbackCreate.

Coverage:
* Valid round-trips (minimal and maximal payloads)
* Constraint enforcement (max_length, ge/le bounds, Prob, enum values)
* Model validators (template_reply iff mode=none, approved_by, target ↔ variant, etc.)
* extra=forbid (inherited from ContractModel)
* Validation errors do not echo input text (hide_input_in_errors)
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ticketward.domain.taxonomy import TAXONOMY_VERSION
from ticketward.schemas.draft import (
    BODY_MAX_CHARS,
    MAX_SENTENCES,
    QUOTE_MAX_CHARS,
    Citation,
    DraftResponse,
    DraftSentence,
    TemplateReply,
)
from ticketward.schemas.feedback import (
    COMMENT_MAX_CHARS,
    EDITED_TEXT_MAX_CHARS,
    FeedbackCreate,
)
from ticketward.schemas.handoff import (
    CSMHandoff,
    EngineeringHandoff,
    HandoffBase,
)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
#  Payload factories
# ---------------------------------------------------------------------------


def model_meta_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "local_ollama",
        "model_name": "tw-triage",
        "model_version": "tw-triage-qwen35-2b-lora@0.1.0",
        "adapter_sha": None,
        "prompt_version": "triage.v1",
        "taxonomy_version": TAXONOMY_VERSION,
        "policy_version": "rules.v1",
        "latency_ms": 800,
        "input_tokens": 1200,
        "output_tokens": 300,
        "cost_usd": "0.000000",
        "repair_attempts": 0,
        "confidence_method": "token_logprob",
        "calibrator_version": None,
        "calibration_fit_run_id": None,
        "decoding_backend": "ollama-0.34.4/llama.cpp-b11081",
        "logprobs_mode": "ollama-raw-pre-grammar",
    }
    payload.update(overrides)
    return payload


def citation_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "citation_id": "c1",
        "doc_id": str(uuid4()),
        "doc_version": 3,
        "chunk_id": "kb_sso_redirect_loop#c1",
        "title": "SSO Redirect Loop Troubleshooting",
        "doc_type": "help_article",
        "url_slug": "/kb/sso-redirect-loop",
        "quote": "Clear the browser cache and check the IdP certificate expiry date.",
        "support_score": 0.92,
    }
    payload.update(overrides)
    return payload


def draft_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "draft_id": str(uuid4()),
        "ticket_id": str(uuid4()),
        "triage_run_id": str(uuid4()),
        "mode": "grounded_answer",
        "sentences": [
            {
                "text": "Please clear your browser cache.",
                "kind": "procedural",
                "citation_ids": ["c1"],
            },
            {
                "text": "I understand how frustrating this is.",
                "kind": "empathy",
                "citation_ids": [],
            },
        ],
        "body_markdown": (
            "Please clear your browser cache [1]."
            " I understand how frustrating this is."
        ),
        "citations": [citation_payload()],
        "template_reply": None,
        "unsupported_sentence_count": 0,
        "generated_by": model_meta_payload(),
        "status": "pending_review",
        "guard_flags": [],
        "created_at": NOW.isoformat(),
    }
    payload.update(overrides)
    return payload


def template_reply_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "template_key": "tpl_security_ack",
        "doc_version": 1,
        "body_markdown": "Thank you for reporting this. Our security team will investigate.",
    }
    payload.update(overrides)
    return payload


def handoff_base_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "handoff_id": str(uuid4()),
        "ticket_id": str(uuid4()),
        "target": "billing",
        "variant": "generic",
        "one_line_summary": "Business customer reports duplicate billing charge.",
        "customer_problem": "Customer was charged twice for the same monthly invoice.",
        "customer_goal": "Get a refund for the duplicate charge.",
        "account_tier": "business",
        "arr_band": "50k-250k",
        "intent": "billing_duplicate_charge",
        "priority": "high",
        "sentiment": "frustrated",
        "churn_risk": "medium",
        "entities": [{"type": "invoice_id", "value": "INV-2026-0912"}],
        "steps_already_attempted": ["Verified payment in Stripe dashboard"],
        "articles_already_checked": ["kb_billing_duplicate_charge"],
        "rationale": "Forced review: critical billing intent with confirmed duplicate.",
        "escalation_reasons": ["forced_category_payment_dispute"],
        "open_questions": ["Is the duplicate charge from a retry or a separate invoice?"],
        "customer_facing_expectation": "A billing specialist will review within 4 hours.",
        "ticket_context_ref": {
            "ticket_id": str(uuid4()),
            "message_count": 3,
            "first_received_at": NOW.isoformat(),
        },
        "edited_by": None,
        "version": 1,
    }
    payload.update(overrides)
    return payload


def csm_handoff_payload(**overrides: Any) -> dict[str, Any]:
    base = handoff_base_payload(
        target="csm",
        variant="csm",
        intent="cancellation_request",
        escalation_reasons=["forced_category_cancellation"],
    )
    base.update(
        {
            "sentiment_trajectory": [
                {"at": NOW.isoformat(), "sentiment": "frustrated"},
            ],
            "issue_history": [
                {
                    "ticket_id": str(uuid4()),
                    "intent": "billing_payment_failure",
                    "status": "resolved",
                    "created_at": NOW.isoformat(),
                }
            ],
            "churn_signals": ["Mentioned competitor by name", "Third complaint in 30 days"],
            "recommended_follow_up": "csm_call_48h",
        }
    )
    base.update(overrides)
    return base


def engineering_handoff_payload(**overrides: Any) -> dict[str, Any]:
    base = handoff_base_payload(
        target="engineering",
        variant="engineering",
        intent="bug_report",
        priority="urgent",
        escalation_reasons=["low_confidence_intent"],
    )
    base.update(
        {
            "reproduction_steps": ["1. Log in via SSO", "2. Click Projects", "3. See 500 error"],
            "expected_behavior": "Projects page loads with the task list.",
            "actual_behavior": "500 Internal Server Error after 12 seconds.",
            "error_codes": ["ERR_API_500", "TIMEOUT_EXCEEDED"],
            "environment": {
                "browser": "Chrome 130",
                "os": "macOS 16.1",
                "app_version": "5.3.2",
                "platform": "web",
                "region": "eu",
            },
            "customer_impact": {
                "users_affected": 45,
                "workspaces_affected": 3,
                "business_impact": "Entire EU engineering team cannot access projects.",
            },
            "first_seen_at": NOW.isoformat(),
            "linked_incident_id": "inc_2026_09_eu_login_degradation",
            "severity_suggestion": "sev2",
        }
    )
    base.update(overrides)
    return base


def feedback_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target_type": "triage_field",
        "target_id": str(uuid4()),
        "field": "priority",
        "action": "edit",
        "corrected_value": "urgent",
        "edited_text": None,
        "flag_reason": None,
        "comment": "Customer is enterprise and outage is org-wide.",
    }
    payload.update(overrides)
    return payload


def error_types(
    excinfo: pytest.ExceptionInfo[ValidationError],
) -> set[tuple[tuple[str | int, ...], str]]:
    return {(tuple(error["loc"]), error["type"]) for error in excinfo.value.errors()}


# ===========================================================================
#  DraftSentence
# ===========================================================================


class TestDraftSentence:
    def test_valid_factual_sentence(self) -> None:
        s = DraftSentence.model_validate(
            {"text": "Check the IdP cert.", "kind": "factual", "citation_ids": ["c1"]}
        )
        assert s.kind == "factual"
        assert s.citation_ids == ["c1"]

    def test_empathy_sentence_needs_no_citations(self) -> None:
        s = DraftSentence.model_validate(
            {"text": "I understand.", "kind": "empathy", "citation_ids": []}
        )
        assert s.citation_ids == []

    def test_text_over_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftSentence.model_validate(
                {"text": "x" * 2001, "kind": "holding", "citation_ids": []}
            )
        assert (("text",), "string_too_long") in error_types(excinfo)

    def test_invalid_kind_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftSentence.model_validate({"text": "hi", "kind": "opinion", "citation_ids": []})
        assert (("kind",), "literal_error") in error_types(excinfo)

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftSentence.model_validate(
                {"text": "hi", "kind": "empathy", "citation_ids": [], "extra": True}
            )
        assert (("extra",), "extra_forbidden") in error_types(excinfo)


# ===========================================================================
#  Citation
# ===========================================================================


class TestCitation:
    def test_valid_citation_round_trips(self) -> None:
        c = Citation.model_validate(citation_payload())
        assert c.doc_type.value == "help_article"
        assert c.support_score == 0.92
        again = Citation.model_validate_json(c.model_dump_json())
        assert again == c

    def test_quote_over_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            Citation.model_validate(citation_payload(quote="q" * (QUOTE_MAX_CHARS + 1)))
        assert (("quote",), "string_too_long") in error_types(excinfo)

    def test_support_score_must_be_a_probability(self) -> None:
        with pytest.raises(ValidationError):
            Citation.model_validate(citation_payload(support_score=1.5))
        with pytest.raises(ValidationError):
            Citation.model_validate(citation_payload(support_score=-0.01))

    def test_doc_version_must_be_positive(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            Citation.model_validate(citation_payload(doc_version=0))
        assert (("doc_version",), "greater_than_equal") in error_types(excinfo)

    def test_invalid_doc_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            Citation.model_validate(citation_payload(doc_type="blog_post"))
        assert (("doc_type",), "enum") in error_types(excinfo)


# ===========================================================================
#  TemplateReply
# ===========================================================================


class TestTemplateReply:
    def test_valid_template_round_trips(self) -> None:
        t = TemplateReply.model_validate(template_reply_payload())
        assert t.template_key == "tpl_security_ack"
        assert t.doc_version == 1
        again = TemplateReply.model_validate_json(t.model_dump_json())
        assert again == t

    def test_template_key_must_be_a_doc_key(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TemplateReply.model_validate(template_reply_payload(template_key="Invalid Key!"))
        assert (("template_key",), "string_pattern_mismatch") in error_types(excinfo)

    def test_body_over_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TemplateReply.model_validate(
                template_reply_payload(body_markdown="x" * (BODY_MAX_CHARS + 1))
            )
        assert (("body_markdown",), "string_too_long") in error_types(excinfo)


# ===========================================================================
#  DraftResponse
# ===========================================================================


class TestDraftResponse:
    def test_valid_grounded_answer_round_trips(self) -> None:
        d = DraftResponse.model_validate(draft_payload())
        assert d.mode == "grounded_answer"
        assert d.template_reply is None
        assert len(d.sentences) == 2
        assert len(d.citations) == 1
        again = DraftResponse.model_validate_json(d.model_dump_json())
        assert again.draft_id == d.draft_id

    def test_mode_none_requires_template_reply(self) -> None:
        with pytest.raises(ValidationError, match="template_reply is required"):
            DraftResponse.model_validate(draft_payload(mode="none", template_reply=None))

    def test_mode_none_with_template_reply_is_valid(self) -> None:
        d = DraftResponse.model_validate(
            draft_payload(mode="none", template_reply=template_reply_payload())
        )
        assert d.mode == "none"
        assert d.template_reply is not None
        assert d.template_reply.template_key == "tpl_security_ack"

    def test_non_none_mode_rejects_template_reply(self) -> None:
        with pytest.raises(ValidationError, match="template_reply must be null"):
            DraftResponse.model_validate(
                draft_payload(mode="grounded_answer", template_reply=template_reply_payload())
            )

    @pytest.mark.parametrize("mode", ["holding_reply_template", "clarifying_questions"])
    def test_other_modes_reject_template_reply(self, mode: str) -> None:
        with pytest.raises(ValidationError, match="template_reply must be null"):
            DraftResponse.model_validate(
                draft_payload(mode=mode, template_reply=template_reply_payload())
            )

    def test_sentences_capped_at_max(self) -> None:
        sentences = [
            {"text": f"S{i}", "kind": "empathy", "citation_ids": []}
            for i in range(MAX_SENTENCES + 1)
        ]
        with pytest.raises(ValidationError) as excinfo:
            DraftResponse.model_validate(draft_payload(sentences=sentences))
        assert (("sentences",), "too_long") in error_types(excinfo)

    def test_body_over_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftResponse.model_validate(draft_payload(body_markdown="x" * (BODY_MAX_CHARS + 1)))
        assert (("body_markdown",), "string_too_long") in error_types(excinfo)

    def test_unsupported_sentence_count_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftResponse.model_validate(draft_payload(unsupported_sentence_count=-1))
        assert (("unsupported_sentence_count",), "greater_than_equal") in error_types(excinfo)

    def test_invalid_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftResponse.model_validate(draft_payload(status="sent"))
        assert (("status",), "literal_error") in error_types(excinfo)

    def test_invalid_guard_flag_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftResponse.model_validate(draft_payload(guard_flags=["unknown_flag"]))
        assert (("guard_flags", 0), "literal_error") in error_types(excinfo)

    @pytest.mark.parametrize(
        "flag",
        [
            "claims_pricing_without_source",
            "claims_account_status",
            "claims_refund_eligibility",
            "claims_incident_status_without_record",
            "claims_capability_without_source",
            "claims_timing_without_source",
            "contains_url_not_in_kb",
            "contains_pii",
            "injection_echo",
        ],
    )
    def test_all_nine_guard_flags_are_accepted(self, flag: str) -> None:
        d = DraftResponse.model_validate(draft_payload(guard_flags=[flag]))
        assert d.guard_flags == [flag]

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            DraftResponse.model_validate(draft_payload(auto_send=True))
        assert (("auto_send",), "extra_forbidden") in error_types(excinfo)

    def test_validation_errors_do_not_echo_draft_text(self) -> None:
        secret = "my-secret-draft-" + "z" * 300
        with pytest.raises(ValidationError) as excinfo:
            DraftResponse.model_validate(draft_payload(status=secret))
        assert secret not in str(excinfo.value)


# ===========================================================================
#  HandoffBase
# ===========================================================================


class TestHandoffBase:
    def test_valid_generic_handoff_round_trips(self) -> None:
        h = HandoffBase.model_validate(handoff_base_payload())
        assert h.target == "billing"
        assert h.variant == "generic"
        assert h.version == 1
        again = HandoffBase.model_validate_json(h.model_dump_json())
        assert again.handoff_id == h.handoff_id

    def test_summary_over_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(handoff_base_payload(one_line_summary="s" * 201))
        assert (("one_line_summary",), "string_too_long") in error_types(excinfo)

    def test_escalation_reasons_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(handoff_base_payload(escalation_reasons=[]))
        assert (("escalation_reasons",), "too_short") in error_types(excinfo)

    def test_invalid_escalation_reason_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(handoff_base_payload(escalation_reasons=["because"]))
        assert (("escalation_reasons", 0), "enum") in error_types(excinfo)

    def test_invalid_target_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(handoff_base_payload(target="marketing"))
        assert (("target",), "literal_error") in error_types(excinfo)

    def test_invalid_variant_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(handoff_base_payload(variant="legal"))
        assert (("variant",), "literal_error") in error_types(excinfo)

    def test_version_must_be_positive(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(handoff_base_payload(version=0))
        assert (("version",), "greater_than_equal") in error_types(excinfo)

    @pytest.mark.parametrize(
        "target", ["csm", "engineering", "billing", "security_privacy", "tier_2"]
    )
    def test_all_targets_are_accepted(self, target: str) -> None:
        h = HandoffBase.model_validate(handoff_base_payload(target=target))
        assert h.target == target

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(handoff_base_payload(auto_route=True))
        assert (("auto_route",), "extra_forbidden") in error_types(excinfo)

    def test_ticket_context_ref_is_validated(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HandoffBase.model_validate(
                handoff_base_payload(
                    ticket_context_ref={
                        "ticket_id": str(uuid4()),
                        "message_count": -1,
                        "first_received_at": NOW.isoformat(),
                    }
                )
            )
        assert (("ticket_context_ref", "message_count"), "greater_than_equal") in error_types(
            excinfo
        )


# ===========================================================================
#  CSMHandoff
# ===========================================================================


class TestCSMHandoff:
    def test_valid_csm_handoff_round_trips(self) -> None:
        h = CSMHandoff.model_validate(csm_handoff_payload())
        assert h.variant == "csm"
        assert h.target == "csm"
        assert h.recommended_follow_up == "csm_call_48h"
        assert len(h.churn_signals) == 2
        again = CSMHandoff.model_validate_json(h.model_dump_json())
        assert again.handoff_id == h.handoff_id

    def test_csm_target_must_be_csm(self) -> None:
        with pytest.raises(ValidationError, match="target must be 'csm'"):
            CSMHandoff.model_validate(csm_handoff_payload(target="billing"))

    def test_invalid_follow_up_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            CSMHandoff.model_validate(csm_handoff_payload(recommended_follow_up="fire_sale"))
        assert (("recommended_follow_up",), "literal_error") in error_types(excinfo)

    @pytest.mark.parametrize(
        "follow_up",
        ["exec_call", "csm_call_48h", "email_check_in", "billing_goodwill_review", "none"],
    )
    def test_all_follow_ups_are_accepted(self, follow_up: str) -> None:
        h = CSMHandoff.model_validate(csm_handoff_payload(recommended_follow_up=follow_up))
        assert h.recommended_follow_up == follow_up

    def test_issue_history_capped(self) -> None:
        entry = {
            "ticket_id": str(uuid4()),
            "intent": "bug_report",
            "status": "resolved",
            "created_at": NOW.isoformat(),
        }
        with pytest.raises(ValidationError) as excinfo:
            CSMHandoff.model_validate(csm_handoff_payload(issue_history=[entry] * 6))
        assert (("issue_history",), "too_long") in error_types(excinfo)


# ===========================================================================
#  EngineeringHandoff
# ===========================================================================


class TestEngineeringHandoff:
    def test_valid_engineering_handoff_round_trips(self) -> None:
        h = EngineeringHandoff.model_validate(engineering_handoff_payload())
        assert h.variant == "engineering"
        assert h.target == "engineering"
        assert h.severity_suggestion == "sev2"
        assert h.customer_impact.users_affected == 45
        again = EngineeringHandoff.model_validate_json(h.model_dump_json())
        assert again.handoff_id == h.handoff_id

    def test_engineering_target_must_be_engineering(self) -> None:
        with pytest.raises(ValidationError, match="target must be 'engineering'"):
            EngineeringHandoff.model_validate(engineering_handoff_payload(target="csm"))

    @pytest.mark.parametrize("sev", ["sev1", "sev2", "sev3", "sev4"])
    def test_all_severities_are_accepted(self, sev: str) -> None:
        h = EngineeringHandoff.model_validate(engineering_handoff_payload(severity_suggestion=sev))
        assert h.severity_suggestion == sev

    def test_invalid_severity_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            EngineeringHandoff.model_validate(
                engineering_handoff_payload(severity_suggestion="sev5")
            )
        assert (("severity_suggestion",), "literal_error") in error_types(excinfo)

    def test_environment_accepts_all_nulls(self) -> None:
        env = {"browser": None, "os": None, "app_version": None, "platform": None, "region": None}
        h = EngineeringHandoff.model_validate(engineering_handoff_payload(environment=env))
        assert h.environment.browser is None

    def test_customer_impact_users_must_be_non_negative(self) -> None:
        impact = {"users_affected": -1, "workspaces_affected": 0, "business_impact": "None"}
        with pytest.raises(ValidationError) as excinfo:
            EngineeringHandoff.model_validate(engineering_handoff_payload(customer_impact=impact))
        assert (("customer_impact", "users_affected"), "greater_than_equal") in error_types(excinfo)

    def test_linked_incident_id_over_limit(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            EngineeringHandoff.model_validate(
                engineering_handoff_payload(linked_incident_id="x" * 129)
            )
        assert (("linked_incident_id",), "string_too_long") in error_types(excinfo)

    def test_reproduction_steps_capped(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            EngineeringHandoff.model_validate(
                engineering_handoff_payload(reproduction_steps=["step"] * 21)
            )
        assert (("reproduction_steps",), "too_long") in error_types(excinfo)


# ===========================================================================
#  FeedbackCreate
# ===========================================================================


class TestFeedbackCreate:
    def test_valid_triage_field_edit_round_trips(self) -> None:
        f = FeedbackCreate.model_validate(feedback_payload())
        assert f.target_type == "triage_field"
        assert f.action == "edit"
        assert f.corrected_value == "urgent"
        again = FeedbackCreate.model_validate_json(f.model_dump_json())
        assert again == f

    def test_field_required_for_triage_field(self) -> None:
        with pytest.raises(ValidationError, match="field is required"):
            FeedbackCreate.model_validate(feedback_payload(field=None))

    def test_field_not_required_for_draft(self) -> None:
        f = FeedbackCreate.model_validate(
            feedback_payload(target_type="draft", field=None, action="accept", corrected_value=None)
        )
        assert f.field is None

    def test_flag_reason_required_for_flag_action(self) -> None:
        with pytest.raises(ValidationError, match="flag_reason is required"):
            FeedbackCreate.model_validate(
                feedback_payload(action="flag", flag_reason=None, corrected_value=None)
            )

    def test_flag_with_reason_is_valid(self) -> None:
        f = FeedbackCreate.model_validate(
            feedback_payload(action="flag", flag_reason="hallucination", corrected_value=None)
        )
        assert f.flag_reason == "hallucination"

    def test_edit_requires_corrected_value_or_edited_text(self) -> None:
        with pytest.raises(ValidationError, match="corrected_value or edited_text"):
            FeedbackCreate.model_validate(
                feedback_payload(action="edit", corrected_value=None, edited_text=None)
            )

    def test_edit_with_edited_text_only_is_valid(self) -> None:
        f = FeedbackCreate.model_validate(
            feedback_payload(
                target_type="draft",
                field=None,
                action="edit",
                corrected_value=None,
                edited_text="Fixed draft text here.",
            )
        )
        assert f.edited_text == "Fixed draft text here."

    @pytest.mark.parametrize("action", ["accept", "edit", "reject", "flag", "override"])
    def test_all_actions_are_accepted(self, action: str) -> None:
        kwargs: dict[str, Any] = {"action": action, "target_type": "draft", "field": None}
        if action == "flag":
            kwargs["flag_reason"] = "unsafe"
            kwargs["corrected_value"] = None
        elif action == "edit":
            kwargs["edited_text"] = "fixed"
        elif action in {"accept", "reject", "override"}:
            kwargs["corrected_value"] = None
        f = FeedbackCreate.model_validate(feedback_payload(**kwargs))
        assert f.action == action

    @pytest.mark.parametrize(
        "target_type",
        ["triage_field", "draft", "citation", "handoff", "policy_decision"],
    )
    def test_all_target_types_are_accepted(self, target_type: str) -> None:
        kwargs: dict[str, Any] = {
            "target_type": target_type,
            "action": "accept",
            "corrected_value": None,
        }
        if target_type == "triage_field":
            kwargs["field"] = "intent"
        else:
            kwargs["field"] = None
        f = FeedbackCreate.model_validate(feedback_payload(**kwargs))
        assert f.target_type == target_type

    @pytest.mark.parametrize(
        "flag_reason",
        [
            "hallucination",
            "wrong_citation",
            "unsafe",
            "tone",
            "pii_leak",
            "outdated_source",
            "other",
        ],
    )
    def test_all_flag_reasons_are_accepted(self, flag_reason: str) -> None:
        f = FeedbackCreate.model_validate(
            feedback_payload(action="flag", flag_reason=flag_reason, corrected_value=None)
        )
        assert f.flag_reason == flag_reason

    @pytest.mark.parametrize(
        "field",
        [
            "intent",
            "priority",
            "sentiment",
            "churn_risk",
            "product_area",
            "recommended_queue",
            "recommended_action",
        ],
    )
    def test_all_feedback_fields_are_accepted(self, field: str) -> None:
        f = FeedbackCreate.model_validate(feedback_payload(field=field))
        assert f.field == field

    def test_comment_over_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FeedbackCreate.model_validate(feedback_payload(comment="c" * (COMMENT_MAX_CHARS + 1)))
        assert (("comment",), "string_too_long") in error_types(excinfo)

    def test_edited_text_over_limit_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FeedbackCreate.model_validate(
                feedback_payload(
                    target_type="draft",
                    field=None,
                    action="edit",
                    corrected_value=None,
                    edited_text="t" * (EDITED_TEXT_MAX_CHARS + 1),
                )
            )
        assert (("edited_text",), "string_too_long") in error_types(excinfo)

    def test_invalid_target_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FeedbackCreate.model_validate(feedback_payload(target_type="model"))
        assert (("target_type",), "literal_error") in error_types(excinfo)

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FeedbackCreate.model_validate(feedback_payload(auto_apply=True))
        assert (("auto_apply",), "extra_forbidden") in error_types(excinfo)

    def test_validation_errors_do_not_echo_input(self) -> None:
        secret = "private-feedback-" + "z" * 300
        with pytest.raises(ValidationError) as excinfo:
            FeedbackCreate.model_validate(feedback_payload(action=secret))
        assert secret not in str(excinfo.value)
