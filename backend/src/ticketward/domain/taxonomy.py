"""Frozen v1 domain taxonomy (spec §5, ``taxonomy_version = "2026-09-v1"``).

Every vocabulary the models, policy engine, database and UI share lives here and is
exported to ``schemas/json/`` for JSON Schema consumers and TypeScript codegen.

Changing ANY member requires an ADR, a new ``TAXONOMY_VERSION``, relabeling,
retraining and a migration (spec §5). The one precedent is spec v1.1: three
system-emitted escalation reasons were added before the P1 freeze as an ADR-0029
amendment, with the version unchanged because nothing was labeled yet.
``tests/unit/test_taxonomy.py`` pins a fingerprint of these enums so an accidental edit
fails CI.

Member names intentionally equal their snake_case wire values (spec §6.1 style).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, unique
from types import MappingProxyType
from typing import Final

TAXONOMY_VERSION: Final = "2026-09-v1"


@unique
class Intent(StrEnum):
    """Primary/secondary customer intent (spec §5.1): 12 intents + reserved fallback."""

    sso_login_failure = "sso_login_failure"
    account_access_issue = "account_access_issue"
    billing_duplicate_charge = "billing_duplicate_charge"
    billing_payment_failure = "billing_payment_failure"
    refund_request = "refund_request"
    cancellation_request = "cancellation_request"
    plan_pricing_inquiry = "plan_pricing_inquiry"
    service_outage = "service_outage"
    bug_report = "bug_report"
    how_to_question = "how_to_question"
    security_report = "security_report"
    privacy_legal_request = "privacy_legal_request"
    other_unclear = "other_unclear"


@unique
class Queue(StrEnum):
    """Work queues (spec §5.2)."""

    general_support_tier_1 = "general_support_tier_1"
    technical_support_tier_2 = "technical_support_tier_2"
    billing_and_accounts = "billing_and_accounts"
    customer_success_retention = "customer_success_retention"
    security_and_privacy = "security_and_privacy"
    incident_response = "incident_response"


@unique
class Priority(StrEnum):
    """Ticket priority (spec §5.3), highest first."""

    urgent = "urgent"
    high = "high"
    normal = "normal"
    low = "low"


@unique
class Sentiment(StrEnum):
    """Customer sentiment of the latest message (spec §5.4). Assistive signal only (L-02)."""

    positive = "positive"
    neutral = "neutral"
    confused = "confused"
    frustrated = "frustrated"
    angry = "angry"


@unique
class ChurnRisk(StrEnum):
    """Churn risk (spec §5.5). Assistive signal only (L-02)."""

    low = "low"
    medium = "medium"
    high = "high"


@unique
class ProductArea(StrEnum):
    """Taskmoor product areas (spec §3)."""

    projects_tasks = "projects_tasks"
    boards_timelines = "boards_timelines"
    sso_identity = "sso_identity"
    user_admin_permissions = "user_admin_permissions"
    billing_subscriptions = "billing_subscriptions"
    integrations_api = "integrations_api"
    notifications_email = "notifications_email"
    mobile_apps = "mobile_apps"
    reporting_analytics = "reporting_analytics"
    automations = "automations"
    data_import_export = "data_import_export"
    platform_availability = "platform_availability"


@unique
class EntityType(StrEnum):
    """Extractable entity types (spec §5.6). PII appears only as masked placeholders."""

    error_code = "error_code"
    http_status = "http_status"
    saml_idp = "saml_idp"
    invoice_id = "invoice_id"
    charge_amount = "charge_amount"
    currency = "currency"
    charge_date = "charge_date"
    workspace_id = "workspace_id"
    account_id = "account_id"
    user_count_affected = "user_count_affected"
    browser = "browser"
    os = "os"
    app_version = "app_version"
    integration_name = "integration_name"
    api_endpoint = "api_endpoint"
    feature_name = "feature_name"
    region = "region"
    timestamp = "timestamp"
    competitor_name = "competitor_name"
    legal_reference = "legal_reference"
    steps_already_tried = "steps_already_tried"


@unique
class SamlIdp(StrEnum):
    """Normalized values for ``saml_idp`` entities (spec §5.6)."""

    okta = "okta"
    azure_ad = "azure_ad"
    google = "google"
    onelogin = "onelogin"
    other = "other"


@unique
class RecommendedAction(StrEnum):
    """``recommended_action`` vocabulary (spec §5.7)."""

    answer_with_kb_article = "answer_with_kb_article"
    request_more_information = "request_more_information"
    request_saml_error_details_and_check_known_incident = (
        "request_saml_error_details_and_check_known_incident"
    )
    check_known_incident_and_share_status = "check_known_incident_and_share_status"
    collect_repro_steps_and_escalate_to_engineering = (
        "collect_repro_steps_and_escalate_to_engineering"
    )
    escalate_to_engineering = "escalate_to_engineering"
    escalate_to_billing_for_review = "escalate_to_billing_for_review"
    escalate_to_csm_retention = "escalate_to_csm_retention"
    escalate_to_security = "escalate_to_security"
    escalate_to_privacy_legal = "escalate_to_privacy_legal"
    offer_human_contact = "offer_human_contact"
    send_password_reset_guidance = "send_password_reset_guidance"  # noqa: S105  # nosec B105
    share_pricing_page_reference = "share_pricing_page_reference"
    link_to_active_incident = "link_to_active_incident"
    route_to_tier_2 = "route_to_tier_2"
    close_as_duplicate_ticket = "close_as_duplicate_ticket"
    no_action_spam = "no_action_spam"


@unique
class EscalationReason(StrEnum):
    """Escalation reasons recorded in ``escalation_reasons[]`` (spec §5.9, v1.1).

    v1.1 added ``critical_category_suspected`` (rule N6), ``queue_overridden_by_rule``
    (rule N1 / §7.3.2) and ``pii_masking_failed`` (rule P7). They are system-emitted, not
    model labels, so ``TAXONOMY_VERSION`` stays ``2026-09-v1`` (ADR-0029 amendment).
    Member order follows the spec list.
    """

    customer_requested_human = "customer_requested_human"
    forced_category_refund = "forced_category_refund"
    forced_category_cancellation = "forced_category_cancellation"
    forced_category_payment_dispute = "forced_category_payment_dispute"
    forced_category_security = "forced_category_security"
    forced_category_legal_threat = "forced_category_legal_threat"
    forced_category_privacy = "forced_category_privacy"
    active_incident = "active_incident"
    critical_category_suspected = "critical_category_suspected"
    low_confidence_intent = "low_confidence_intent"
    low_confidence_queue = "low_confidence_queue"
    queue_overridden_by_rule = "queue_overridden_by_rule"
    insufficient_evidence = "insufficient_evidence"
    stale_evidence_only = "stale_evidence_only"
    conflicting_evidence = "conflicting_evidence"
    schema_invalid_after_repair = "schema_invalid_after_repair"
    prompt_injection_suspected = "prompt_injection_suspected"
    unsupported_language = "unsupported_language"
    high_churn_risk_high_value = "high_churn_risk_high_value"
    retention_risk = "retention_risk"
    pii_heavy_content = "pii_heavy_content"
    pii_masking_failed = "pii_masking_failed"
    input_truncated = "input_truncated"
    model_unavailable = "model_unavailable"
    agent_initiated = "agent_initiated"


@unique
class PlanTier(StrEnum):
    """Taskmoor plan tiers (spec §3, §6.1)."""

    free = "free"
    starter = "starter"
    business = "business"
    enterprise = "enterprise"


@unique
class Channel(StrEnum):
    """Ticket source channel (spec §6.1). Metadata only at runtime (NG-06)."""

    web_form = "web_form"
    email = "email"
    api = "api"
    chat_transcript = "chat_transcript"


@unique
class DocType(StrEnum):
    """Knowledge-base document types (spec §8.1)."""

    help_article = "help_article"
    policy = "policy"
    product_doc = "product_doc"
    known_incident = "known_incident"
    escalation_runbook = "escalation_runbook"
    reply_template = "reply_template"


CRITICAL_INTENTS: Final[frozenset[Intent]] = frozenset(
    {
        Intent.security_report,  # security
        Intent.service_outage,  # widespread outage
        Intent.cancellation_request,  # cancellation
        Intent.billing_duplicate_charge,  # duplicate charge
        Intent.billing_payment_failure,  # payment failure
    }
)
"""Critical categories for the brief §9 recall metric (spec §5.1, M-03c)."""

FORCED_REVIEW_INTENTS: Final[frozenset[Intent]] = frozenset(
    {
        Intent.billing_duplicate_charge,
        Intent.billing_payment_failure,
        Intent.refund_request,
        Intent.cancellation_request,
        Intent.service_outage,
        Intent.security_report,
        Intent.privacy_legal_request,
    }
)
"""Intents that always require a human decision (spec §5.1 "Forced review?", S-03).

The policy engine evaluates this on the union of primary and secondary intents (§5.1).
"""

FRONTIER_DENYLIST: Final[frozenset[Intent]] = frozenset(
    {Intent.security_report, Intent.privacy_legal_request}
)
"""Intents that must never be sent to a frontier model (spec §7.2, §7.5, S-08)."""


@dataclass(frozen=True, slots=True)
class RoutingDefault:
    """Default queue and action for an intent (spec §5.8).

    Attributes:
        queue: Queue the ticket is routed to unless an allowed override applies.
        action: Recommended first action.
    """

    queue: Queue
    action: RecommendedAction


DEFAULT_ROUTING: Final[Mapping[Intent, RoutingDefault]] = MappingProxyType(
    {
        Intent.sso_login_failure: RoutingDefault(
            Queue.technical_support_tier_2,
            RecommendedAction.request_saml_error_details_and_check_known_incident,
        ),
        Intent.account_access_issue: RoutingDefault(
            Queue.general_support_tier_1, RecommendedAction.send_password_reset_guidance
        ),
        Intent.billing_duplicate_charge: RoutingDefault(
            Queue.billing_and_accounts, RecommendedAction.escalate_to_billing_for_review
        ),
        Intent.billing_payment_failure: RoutingDefault(
            Queue.billing_and_accounts, RecommendedAction.escalate_to_billing_for_review
        ),
        Intent.refund_request: RoutingDefault(
            Queue.billing_and_accounts, RecommendedAction.escalate_to_billing_for_review
        ),
        Intent.cancellation_request: RoutingDefault(
            Queue.customer_success_retention, RecommendedAction.escalate_to_csm_retention
        ),
        Intent.plan_pricing_inquiry: RoutingDefault(
            Queue.general_support_tier_1, RecommendedAction.share_pricing_page_reference
        ),
        Intent.service_outage: RoutingDefault(
            Queue.incident_response, RecommendedAction.check_known_incident_and_share_status
        ),
        Intent.bug_report: RoutingDefault(
            Queue.technical_support_tier_2,
            RecommendedAction.collect_repro_steps_and_escalate_to_engineering,
        ),
        Intent.how_to_question: RoutingDefault(
            Queue.general_support_tier_1, RecommendedAction.answer_with_kb_article
        ),
        Intent.security_report: RoutingDefault(
            Queue.security_and_privacy, RecommendedAction.escalate_to_security
        ),
        Intent.privacy_legal_request: RoutingDefault(
            Queue.security_and_privacy, RecommendedAction.escalate_to_privacy_legal
        ),
        Intent.other_unclear: RoutingDefault(
            Queue.general_support_tier_1, RecommendedAction.request_more_information
        ),
    }
)
"""Seed for the versioned, ops-editable ``routing_rules`` table (spec §5.8)."""

TAXONOMY_ENUMS: Final[tuple[type[StrEnum], ...]] = (
    Intent,
    Queue,
    Priority,
    Sentiment,
    ChurnRisk,
    ProductArea,
    EntityType,
    SamlIdp,
    RecommendedAction,
    EscalationReason,
    PlanTier,
    Channel,
    DocType,
)
"""Every frozen vocabulary, in export order (JSON Schema and fingerprint)."""
