import warnings
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ticketward.domain.taxonomy import TAXONOMY_VERSION, Intent, PlanTier
from ticketward.schemas.problem import ErrorCode, FieldError, ProblemDetail
from ticketward.schemas.ticket import MESSAGE_MAX_CHARS, TicketCreate
from ticketward.schemas.triage import TriageModelOutput, TriageResult

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def ticket_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "customer_tier": "business",
        "channel": "email",
        "subject": "Okta SSO redirect loop",
        "message": "Our whole org is stuck in an Okta SSO redirect loop since 9am.",
    }
    payload.update(overrides)
    return payload


def triage_output_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "intent": "sso_login_failure",
        "secondary_intents": [],
        "priority": "high",
        "sentiment": "frustrated",
        "churn_risk": "medium",
        "churn_signals": ["third time this month"],
        "product_area": "sso_identity",
        "entities": [{"type": "saml_idp", "value": "okta"}],
        "recommended_queue": "technical_support_tier_2",
        "recommended_action": "request_saml_error_details_and_check_known_incident",
        "customer_requested_human": False,
        "information_sufficient": True,
        "rationale": "Org-wide SSO loop on Okta; tier-2 handles SAML misconfiguration.",
    }
    payload.update(overrides)
    return payload


def model_meta_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "local_ollama",
        "model_name": "tw-triage",
        "model_version": "tw-triage-qwen35-2b-lora@0.1.0",
        "adapter_sha": None,
        "prompt_version": "triage.v1",
        "taxonomy_version": TAXONOMY_VERSION,
        "policy_version": "rules.v1",
        "latency_ms": 1200,
        "input_tokens": 480,
        "output_tokens": 160,
        "cost_usd": "0.000000",
        "repair_attempts": 0,
        "confidence_method": "token_logprob",
        "calibrator_version": "calibrator.v1",
        "calibration_fit_run_id": str(uuid4()),
        "decoding_backend": "ollama-0.34.4/llama.cpp-b11081",
        "logprobs_mode": "ollama-raw-pre-grammar",
    }
    payload.update(overrides)
    return payload


def triage_result_payload(**overrides: Any) -> dict[str, Any]:
    payload = triage_output_payload()
    payload.update(
        {
            "entities": [
                {"type": "saml_idp", "value": "okta", "source_span": {"start": 12, "end": 16}}
            ],
            "ticket_id": str(uuid4()),
            "triage_run_id": str(uuid4()),
            "confidence": {
                "intent": 0.93,
                "priority": 0.81,
                "sentiment": 0.77,
                "churn_risk": 0.66,
                "product_area": 0.9,
                "recommended_queue": 0.88,
                "p_critical": 0.04,
            },
            "citations": ["kb_sso_redirect_loop"],
            "needs_human_review": False,
            "escalation_reasons": [],
            "policy_decision": "local_draft",
            "handoff_summary": "Business-tier customer reports an org-wide Okta SSO redirect loop.",
            "matched_incident_id": None,
            "model": model_meta_payload(),
            "created_at": NOW.isoformat(),
        }
    )
    payload.update(overrides)
    return payload


def error_types(
    excinfo: pytest.ExceptionInfo[ValidationError],
) -> set[tuple[tuple[str | int, ...], str]]:
    return {(tuple(error["loc"]), error["type"]) for error in excinfo.value.errors()}


class TestTicketCreate:
    def test_minimal_ticket_is_valid_and_stripped(self) -> None:
        ticket = TicketCreate.model_validate(ticket_payload(subject="  Help  "))
        assert ticket.subject == "Help"
        assert ticket.customer_tier is PlanTier.business
        assert ticket.previous_messages == []

    def test_full_ticket_is_valid(self) -> None:
        ticket = TicketCreate.model_validate(
            ticket_payload(
                external_id="email-123",
                previous_messages=[
                    {"author": "agent", "body": "Try again", "sent_at": NOW.isoformat()}
                ],
                customer_email="it-admin@example.com",
                account={
                    "account_id": "acct_0042",
                    "company_name": "Northwind Synthetic Ltd",
                    "arr_band": "50k-250k",
                    "region": "eu",
                    "seats": 120,
                    "csm_owner_id": str(uuid4()),
                },
                product={
                    "product_area_hint": "sso_identity",
                    "app_version": "5.2.1",
                    "platform": "web",
                },
                received_at=NOW.isoformat(),
            )
        )
        assert ticket.account is not None
        assert ticket.account.arr_band == "50k-250k"

    @pytest.mark.parametrize(
        ("overrides", "loc", "error_type"),
        [
            ({"unexpected": 1}, ("unexpected",), "extra_forbidden"),
            ({"subject": "s" * 301}, ("subject",), "string_too_long"),
            ({"subject": "   "}, ("subject",), "string_too_short"),
            ({"message": "m" * (MESSAGE_MAX_CHARS + 1)}, ("message",), "string_too_long"),
            ({"external_id": "e" * 129}, ("external_id",), "string_too_long"),
            ({"customer_tier": "platinum"}, ("customer_tier",), "enum"),
            ({"channel": "phone"}, ("channel",), "enum"),
            ({"customer_email": "not-an-email"}, ("customer_email",), "value_error"),
            ({"received_at": "2026-09-26T12:00:00"}, ("received_at",), "timezone_aware"),
            (
                {"account": {"account_id": "acct_!!"}},
                ("account", "account_id"),
                "string_pattern_mismatch",
            ),
            (
                {"account": {"account_id": "acct_0042", "seats": 0}},
                ("account", "seats"),
                "greater_than_equal",
            ),
            (
                {"account": {"account_id": "acct_0042", "extra": 1}},
                ("account", "extra"),
                "extra_forbidden",
            ),
            ({"product": {"platform": "linux"}}, ("product", "platform"), "literal_error"),
            (
                {"previous_messages": [{"author": "bot", "body": "x", "sent_at": NOW.isoformat()}]},
                ("previous_messages", 0, "author"),
                "literal_error",
            ),
        ],
    )
    def test_invalid_tickets_are_rejected(
        self, overrides: dict[str, Any], loc: tuple[str | int, ...], error_type: str
    ) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TicketCreate.model_validate(ticket_payload(**overrides))
        assert (loc, error_type) in error_types(excinfo)

    def test_history_is_capped_at_fifty_messages(self) -> None:
        history = [{"author": "customer", "body": "again", "sent_at": NOW.isoformat()}] * 51
        with pytest.raises(ValidationError) as excinfo:
            TicketCreate.model_validate(ticket_payload(previous_messages=history))
        assert (("previous_messages",), "too_long") in error_types(excinfo)

    def test_validation_errors_do_not_echo_ticket_text(self) -> None:
        secret = "my-private-ticket-text-" + "z" * 300
        with pytest.raises(ValidationError) as excinfo:
            TicketCreate.model_validate(ticket_payload(subject=secret))
        assert secret not in str(excinfo.value)
        assert "input_value" not in str(excinfo.value)


class TestTriageContracts:
    def test_model_output_round_trips_in_strict_json_mode(self) -> None:
        output = TriageModelOutput.model_validate(triage_output_payload())
        assert output.intent is Intent.sso_login_failure
        again = TriageModelOutput.model_validate_json(output.model_dump_json(), strict=True)
        assert again == output

    @pytest.mark.parametrize(
        ("overrides", "loc", "error_type"),
        [
            ({"intent": "refund"}, ("intent",), "enum"),
            ({"secondary_intents": ["bug_report"] * 3}, ("secondary_intents",), "too_long"),
            ({"churn_signals": ["a"] * 6}, ("churn_signals",), "too_long"),
            ({"churn_signals": ["x" * 201]}, ("churn_signals", 0), "string_too_long"),
            ({"entities": [{"type": "error_code", "value": "E1"}] * 21}, ("entities",), "too_long"),
            ({"entities": [{"type": "ssn", "value": "x"}]}, ("entities", 0, "type"), "enum"),
            (
                {"entities": [{"type": "error_code", "value": "v" * 201}]},
                ("entities", 0, "value"),
                "string_too_long",
            ),
            ({"rationale": "r" * 401}, ("rationale",), "string_too_long"),
            ({"chain_of_thought": "..."}, ("chain_of_thought",), "extra_forbidden"),
        ],
    )
    def test_invalid_model_output_is_rejected(
        self, overrides: dict[str, Any], loc: tuple[str | int, ...], error_type: str
    ) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TriageModelOutput.model_validate(triage_output_payload(**overrides))
        assert (loc, error_type) in error_types(excinfo)

    def test_required_fields_have_no_defaults(self) -> None:
        payload = triage_output_payload()
        del payload["customer_requested_human"]
        with pytest.raises(ValidationError) as excinfo:
            TriageModelOutput.model_validate(payload)
        assert (("customer_requested_human",), "missing") in error_types(excinfo)

    def test_triage_result_is_valid_and_serializes(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = TriageResult.model_validate(triage_result_payload())
        dumped = result.model_dump(mode="json")
        assert dumped["model"]["schema_version"] == "triage.v1"
        assert dumped["model"]["cost_usd"] == "0.000000"
        assert result.model.cost_usd == Decimal(0)

    @pytest.mark.parametrize(
        ("overrides", "loc", "error_type"),
        [
            ({"citations": ["KB Article!"]}, ("citations", 0), "string_pattern_mismatch"),
            ({"handoff_summary": "h" * 1201}, ("handoff_summary",), "string_too_long"),
            ({"escalation_reasons": ["because"]}, ("escalation_reasons", 0), "enum"),
            ({"policy_decision": "auto_send"}, ("policy_decision",), "literal_error"),
            ({"created_at": "2026-09-26T12:00:00"}, ("created_at",), "timezone_aware"),
        ],
    )
    def test_invalid_triage_result_is_rejected(
        self, overrides: dict[str, Any], loc: tuple[str | int, ...], error_type: str
    ) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(triage_result_payload(**overrides))
        assert (loc, error_type) in error_types(excinfo)

    @pytest.mark.parametrize(
        "field",
        [
            "intent",
            "priority",
            "sentiment",
            "churn_risk",
            "product_area",
            "recommended_queue",
            "p_critical",
        ],
    )
    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_every_confidence_field_is_a_probability(self, field: str, value: float) -> None:
        # v1.1 A-29: all FieldConfidence fields bounded 0..1, including p_critical.
        payload = triage_result_payload()
        payload["confidence"][field] = value
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(payload)
        assert {error["loc"] for error in excinfo.value.errors()} == {("confidence", field)}

    def test_p_critical_is_required(self) -> None:
        payload = triage_result_payload()
        del payload["confidence"]["p_critical"]
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(payload)
        assert (("confidence", "p_critical"), "missing") in error_types(excinfo)

    def test_model_output_never_carries_spans(self) -> None:
        entity = {"type": "saml_idp", "value": "okta", "source_span": {"start": 0, "end": 4}}
        with pytest.raises(ValidationError) as excinfo:
            TriageModelOutput.model_validate(triage_output_payload(entities=[entity]))
        assert (("entities", 0, "source_span"), "extra_forbidden") in error_types(excinfo)

    def test_result_entities_carry_server_spans(self) -> None:
        result = TriageResult.model_validate(triage_result_payload())
        span = result.entities[0].source_span
        assert span is not None
        assert (span.start, span.end) == (12, 16)
        unmatched = triage_result_payload(
            entities=[{"type": "error_code", "value": "SAML_ERR_302", "source_span": None}]
        )
        assert TriageResult.model_validate(unmatched).entities[0].source_span is None

    @pytest.mark.parametrize(
        ("entity", "loc", "error_type"),
        [
            ({"type": "saml_idp", "value": "okta"}, ("entities", 0, "source_span"), "missing"),
            (
                {"type": "saml_idp", "value": "okta", "source_span": {"start": -1, "end": 3}},
                ("entities", 0, "source_span", "start"),
                "greater_than_equal",
            ),
            (
                {"type": "saml_idp", "value": "okta", "source_span": {"start": 9, "end": 4}},
                ("entities", 0, "source_span"),
                "value_error",
            ),
        ],
    )
    def test_invalid_spans_are_rejected(
        self, entity: dict[str, Any], loc: tuple[str | int, ...], error_type: str
    ) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(triage_result_payload(entities=[entity]))
        assert (loc, error_type) in error_types(excinfo)

    def test_result_entities_are_capped(self) -> None:
        entity = {"type": "error_code", "value": "E1", "source_span": None}
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(triage_result_payload(entities=[entity] * 21))
        assert (("entities",), "too_long") in error_types(excinfo)

    def test_model_output_may_repeat_secondary_intents_before_repair(self) -> None:
        # Post-validation check (repair level 1 dedupes), so parsing must still succeed.
        output = TriageModelOutput.model_validate(
            triage_output_payload(secondary_intents=["sso_login_failure", "sso_login_failure"])
        )
        assert output.secondary_intents == [Intent.sso_login_failure, Intent.sso_login_failure]

    @pytest.mark.parametrize(
        "secondary",
        [["bug_report", "bug_report"], ["sso_login_failure"], ["bug_report", "sso_login_failure"]],
    )
    def test_result_requires_repaired_secondary_intents(self, secondary: list[str]) -> None:
        with pytest.raises(ValidationError, match="secondary_intents must be unique"):
            TriageResult.model_validate(triage_result_payload(secondary_intents=secondary))

    def test_result_accepts_distinct_secondary_intents(self) -> None:
        result = TriageResult.model_validate(
            triage_result_payload(secondary_intents=["plan_pricing_inquiry", "bug_report"])
        )
        assert result.secondary_intents == [Intent.plan_pricing_inquiry, Intent.bug_report]

    @pytest.mark.parametrize(
        "overrides",
        [
            {"cost_usd": "-0.01"},
            {"latency_ms": -1},
            {"provider": "openai"},
            {"confidence_method": "vibes"},
        ],
    )
    def test_invalid_model_meta_is_rejected(self, overrides: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            TriageResult.model_validate(
                triage_result_payload(model=model_meta_payload(**overrides))
            )

    @pytest.mark.parametrize(
        "field",
        [
            "adapter_sha",
            "calibrator_version",
            "calibration_fit_run_id",
            "decoding_backend",
            "logprobs_mode",
        ],
    )
    def test_model_meta_nullable_fields_are_still_required(self, field: str) -> None:
        meta = model_meta_payload()
        del meta[field]
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(triage_result_payload(model=meta))
        assert (("model", field), "missing") in error_types(excinfo)

    def test_model_meta_v1_1_fields_accept_null_for_uncalibrated_baselines(self) -> None:
        meta = model_meta_payload(
            provider="rules_baseline",
            confidence_method="calibrated_softmax",
            calibrator_version=None,
            calibration_fit_run_id=None,
            decoding_backend=None,
            logprobs_mode=None,
        )
        result = TriageResult.model_validate(triage_result_payload(model=meta))
        assert result.model.calibration_fit_run_id is None

    def test_model_meta_calibration_run_id_must_be_a_uuid(self) -> None:
        meta = model_meta_payload(calibration_fit_run_id="run-42")
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(triage_result_payload(model=meta))
        assert (("model", "calibration_fit_run_id"), "uuid_parsing") in error_types(excinfo)


class TestProblemDetail:
    def test_optional_members_are_omitted_when_empty(self) -> None:
        problem = ProblemDetail(
            type="/problems/not-found",
            title="Resource not found",
            status=404,
            detail="The requested resource was not found.",
            code=ErrorCode.NOT_FOUND,
        )
        assert set(problem.model_dump(exclude_none=True)) == {
            "type",
            "title",
            "status",
            "detail",
            "code",
        }

    def test_field_errors_are_bounded(self) -> None:
        with pytest.raises(ValidationError):
            FieldError(loc=["body"], msg="m" * 257, type="value_error")

    def test_status_must_be_http_status(self) -> None:
        with pytest.raises(ValidationError):
            ProblemDetail(
                type="about:blank", title="x", status=700, detail="x", code=ErrorCode.INTERNAL
            )
