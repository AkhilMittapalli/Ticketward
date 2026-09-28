"""Frozen v1 domain taxonomy (spec §5, ``taxonomy_version = "2026-09-v1"``).

Every ticket and triage vocabulary the models, policy engine, database and UI share lives
here and is exported to ``schemas/json/`` for JSON Schema consumers and TypeScript codegen.

Changing ANY member requires an ADR, a new ``TAXONOMY_VERSION``, relabeling,
retraining and a migration (spec §5). The one precedent is spec v1.1: three
system-emitted escalation reasons were added before the P1 freeze as an ADR-0029
amendment, with the version unchanged because nothing was labeled yet.
``tests/unit/test_taxonomy.py`` pins a fingerprint of these enums so an accidental edit
fails CI.

Member names intentionally equal their snake_case wire values (spec §6.1 style).

The module also freezes the v1 policy tables that spec §5 defines next to the enums (P1.5):

* §5.8 routing: the default queue and action per intent plus the override allow-lists
  (``ROUTING_OVERRIDES``), the seed of the versioned ``routing_rules`` table (§10);
* §5.9 escalation reasons: the named emitter of every reason (``EMITTER_BY_REASON``);
* §5.3 priority and SLA: first-response and resolution targets with the §3 plan multiplier
  (``sla_targets``) and the rule-N3 priority floors (``apply_priority_floors``).

These tables are data plus pure functions, like the rest of the domain layer. They are not
exported to ``schemas/json/``, which carries the vocabularies only (``TAXONOMY_ENUMS``).
Values the spec leaves open are marked "Spec-silent" or "Spec-ambiguous" where they are
defined, together with the conservative choice made. ``tests/unit/test_taxonomy_*.py`` pin
every table against an independent copy of the spec, and
``tests/contract/test_taxonomy_parity.py`` keeps the ml copies in ``data/spec/`` in sync.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
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

HUMAN_REQUEST_ACTION: Final = RecommendedAction.offer_human_contact
"""Action rule P1 sets for any intent when the customer asks for a person (spec §7.3, S-02)."""

# Spec-silent: the spec never lists "self-service" actions. These close a ticket or answer it
# from documentation without a specialist's decision, so a forced-review intent (S-03) must not
# get one; it is the ml set `self_serve_actions` (docs/labeling_guidelines.md R11).
SELF_SERVE_ACTIONS: Final[frozenset[RecommendedAction]] = frozenset(
    {
        RecommendedAction.answer_with_kb_article,
        RecommendedAction.share_pricing_page_reference,
        RecommendedAction.send_password_reset_guidance,
        RecommendedAction.no_action_spam,
        RecommendedAction.close_as_duplicate_ticket,
    }
)
"""Actions that resolve a ticket without a specialist; never allowed for forced-review intents."""


@dataclass(frozen=True, slots=True)
class RoutingOverrides:
    """Alternates accepted instead of an intent's §5.8 default queue and action.

    Attributes:
        queues: Alternate queues. Rule N1 keeps the model's ``recommended_queue`` only if it is
            the default or one of these AND queue confidence >= tau_queue; otherwise the default
            wins with ``queue_overridden_by_rule`` (spec §5.8, §7.3). Seeds
            ``routing_rules.allowed_alt_queues`` (spec §10).
        actions: Alternate actions that label QA accepts for the intent (rule R3, spec §9.1).
            The spec defines no runtime override of the action; rule P1 sets
            ``HUMAN_REQUEST_ACTION`` for every intent on its own.
    """

    queues: frozenset[Queue] = frozenset()
    actions: frozenset[RecommendedAction] = frozenset()


_DEFAULTS_ONLY: Final = RoutingOverrides()

# Spec §5.8 names one alternate: sso_login_failure -> {tier_2, incident_response} (an org-wide
# SSO failure can be an outage, §5.1). Spec-silent for every other intent, so the conservative
# choice is no alternate: the rule default always wins, and incidents, security and privacy
# reach their queues through the §7.3.2 forced-queue rows instead. The one action alternate is
# derived: spam belongs to other_unclear (§5.1), no_action_spam is the spam action (§5.7), and
# labeling guideline R13 labels it so.
ROUTING_OVERRIDES: Final[Mapping[Intent, RoutingOverrides]] = MappingProxyType(
    {
        Intent.sso_login_failure: RoutingOverrides(queues=frozenset({Queue.incident_response})),
        Intent.account_access_issue: _DEFAULTS_ONLY,
        Intent.billing_duplicate_charge: _DEFAULTS_ONLY,
        Intent.billing_payment_failure: _DEFAULTS_ONLY,
        Intent.refund_request: _DEFAULTS_ONLY,
        Intent.cancellation_request: _DEFAULTS_ONLY,
        Intent.plan_pricing_inquiry: _DEFAULTS_ONLY,
        Intent.service_outage: _DEFAULTS_ONLY,
        Intent.bug_report: _DEFAULTS_ONLY,
        Intent.how_to_question: _DEFAULTS_ONLY,
        Intent.security_report: _DEFAULTS_ONLY,
        Intent.privacy_legal_request: _DEFAULTS_ONLY,
        Intent.other_unclear: RoutingOverrides(
            actions=frozenset({RecommendedAction.no_action_spam})
        ),
    }
)
"""§5.8 override allow-lists per intent (v1 seed; ml copy: ``data/spec/label_rules.v1.yaml``)."""


def default_route(intent: Intent) -> RoutingDefault:
    """Return the §5.8 default queue and action for an intent.

    Args:
        intent: Primary intent.

    Returns:
        The rule default.
    """
    return DEFAULT_ROUTING[intent]


def allowed_overrides(intent: Intent) -> RoutingOverrides:
    """Return the alternates accepted instead of an intent's default (spec §5.8).

    Args:
        intent: Primary intent.

    Returns:
        The alternate queues and actions; both exclude the default.
    """
    return ROUTING_OVERRIDES[intent]


def allowed_queues(intent: Intent) -> frozenset[Queue]:
    """Return every queue rule N1 may keep for an intent: the default plus its alternates.

    Args:
        intent: Primary intent.

    Returns:
        The default queue together with the alternates (the spec §7.3 invariant
        ``final_queue in {default} | allowed_alternates(intent)``, forced queues aside).
    """
    return frozenset({DEFAULT_ROUTING[intent].queue}) | ROUTING_OVERRIDES[intent].queues


def allowed_actions(intent: Intent) -> frozenset[RecommendedAction]:
    """Return the default action of an intent plus its alternates.

    Rule P1's ``HUMAN_REQUEST_ACTION`` applies to every intent and is not repeated here.

    Args:
        intent: Primary intent.

    Returns:
        The default and alternate actions.
    """
    return frozenset({DEFAULT_ROUTING[intent].action}) | ROUTING_OVERRIDES[intent].actions


@unique
class ReasonEmitter(StrEnum):
    """What adds a reason to ``escalation_reasons[]`` (spec §5.9 emitter table).

    Rule ids of the §7.3 decision table that emit reasons (P10, P11 and N3 emit none), plus the
    user escalation endpoint ``POST /tickets/{id}/escalations`` (spec §11).
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"
    P6 = "P6"
    P7 = "P7"
    P8 = "P8"
    P9 = "P9"
    N1 = "N1"
    N2 = "N2"
    N4 = "N4"
    N5 = "N5"
    N6 = "N6"
    N7 = "N7"
    # Spec-silent identifier: the spec names the endpoint but gives it no id.
    escalations_api = "escalations_api"


# One row per reason, in EscalationReason order, so no reason can have two emitters.
# Spec-ambiguous: `queue_overridden_by_rule` is "N1 (and §7.3.2 queue selection)" in the spec.
# The queue step applies N1's allow-list and the forced-queue rows together, so the reason is
# recorded under N1 as its single emitter.
EMITTER_BY_REASON: Final[Mapping[EscalationReason, ReasonEmitter]] = MappingProxyType(
    {
        EscalationReason.customer_requested_human: ReasonEmitter.P1,
        EscalationReason.forced_category_refund: ReasonEmitter.P5,
        EscalationReason.forced_category_cancellation: ReasonEmitter.P5,
        EscalationReason.forced_category_payment_dispute: ReasonEmitter.P5,
        EscalationReason.forced_category_security: ReasonEmitter.P2,
        EscalationReason.forced_category_legal_threat: ReasonEmitter.P3,
        EscalationReason.forced_category_privacy: ReasonEmitter.P3,
        EscalationReason.active_incident: ReasonEmitter.P4,
        EscalationReason.critical_category_suspected: ReasonEmitter.N6,
        EscalationReason.low_confidence_intent: ReasonEmitter.P8,
        EscalationReason.low_confidence_queue: ReasonEmitter.N1,
        EscalationReason.queue_overridden_by_rule: ReasonEmitter.N1,
        EscalationReason.insufficient_evidence: ReasonEmitter.P9,
        EscalationReason.stale_evidence_only: ReasonEmitter.P9,
        EscalationReason.conflicting_evidence: ReasonEmitter.P9,
        EscalationReason.schema_invalid_after_repair: ReasonEmitter.P7,
        EscalationReason.prompt_injection_suspected: ReasonEmitter.P0,
        EscalationReason.unsupported_language: ReasonEmitter.P6,
        EscalationReason.high_churn_risk_high_value: ReasonEmitter.N2,
        EscalationReason.retention_risk: ReasonEmitter.N7,
        EscalationReason.pii_heavy_content: ReasonEmitter.N5,
        EscalationReason.pii_masking_failed: ReasonEmitter.P7,
        EscalationReason.input_truncated: ReasonEmitter.N4,
        EscalationReason.model_unavailable: ReasonEmitter.P7,
        EscalationReason.agent_initiated: ReasonEmitter.escalations_api,
    }
)
"""The single named emitter of every escalation reason (spec §5.9; W-5, I-10)."""

REASONS_BY_EMITTER: Final[Mapping[ReasonEmitter, frozenset[EscalationReason]]] = MappingProxyType(
    {
        emitter: frozenset(r for r, e in EMITTER_BY_REASON.items() if e is emitter)
        for emitter in ReasonEmitter
    }
)
"""The §5.9 table read by emitter: the only reasons each emitter may add."""

_FORCED_RULES: Final[frozenset[ReasonEmitter]] = frozenset(
    {ReasonEmitter.P1, ReasonEmitter.P2, ReasonEmitter.P3, ReasonEmitter.P4, ReasonEmitter.P5}
)

FORCED_REASONS: Final[frozenset[EscalationReason]] = frozenset(
    reason for reason, emitter in EMITTER_BY_REASON.items() if emitter in _FORCED_RULES
)
"""Reasons of the forced rules P1-P5; any of them sets ``needs_human_review`` (spec §7.3.1)."""

# Spec §7.3 rules P2-P5 (the "Effect" column). P3 records forced_category_privacy for the
# intent (or privacy terms); duplicate charge and payment failure share one reason (D6-6).
FORCED_REVIEW_REASON: Final[Mapping[Intent, EscalationReason]] = MappingProxyType(
    {
        Intent.security_report: EscalationReason.forced_category_security,
        Intent.privacy_legal_request: EscalationReason.forced_category_privacy,
        Intent.service_outage: EscalationReason.active_incident,
        Intent.refund_request: EscalationReason.forced_category_refund,
        Intent.cancellation_request: EscalationReason.forced_category_cancellation,
        Intent.billing_duplicate_charge: EscalationReason.forced_category_payment_dispute,
        Intent.billing_payment_failure: EscalationReason.forced_category_payment_dispute,
    }
)
"""The reason a forced-review intent's rule records when that intent is present (spec §7.3).

This is "its forced reason" of the system-level critical-recall rule (spec §9.12 D6-6).
``forced_category_legal_threat`` has no intent: only the P3 threat lexicon emits it.
"""


def emitter_of(reason: EscalationReason) -> ReasonEmitter:
    """Return the component that emits an escalation reason (spec §5.9).

    Args:
        reason: Escalation reason.

    Returns:
        Its single named emitter.
    """
    return EMITTER_BY_REASON[reason]


def reasons_emitted_by(emitter: ReasonEmitter) -> frozenset[EscalationReason]:
    """Return the reasons an emitter may add (spec §5.9).

    Args:
        emitter: Rule id or the escalation endpoint.

    Returns:
        The reasons whose named emitter it is (never empty).
    """
    return REASONS_BY_EMITTER[emitter]


@unique
class SlaUnit(StrEnum):
    """Unit an SLA target is stated in (spec §5.3)."""

    hours = "hours"
    # Spec-silent: the spec defines no business calendar (hours per day, time zone, holidays,
    # or whether the 24/7 enterprise entitlement of §3 counts every day). Targets keep the unit;
    # turning them into a wall-clock `sla_due_at` is left to the service that owns the calendar.
    business_days = "business_days"


@dataclass(frozen=True, slots=True)
class SlaDuration:
    """An SLA target in the unit the spec states it in.

    Attributes:
        amount: Positive, finite amount of ``unit``.
        unit: Wall-clock hours or business days.
    """

    amount: Decimal
    unit: SlaUnit

    def __post_init__(self) -> None:
        """Reject amounts that cannot be a target.

        Raises:
            ValueError: If ``amount`` is not a positive, finite number.
        """
        if not (self.amount.is_finite() and self.amount > 0):
            msg = f"SLA amount must be positive and finite, got {self.amount}"
            raise ValueError(msg)

    def scaled(self, factor: Decimal) -> "SlaDuration":
        """Return this target multiplied by ``factor``, in the same unit.

        Args:
            factor: Positive plan multiplier.

        Returns:
            The scaled target.

        Raises:
            ValueError: If ``factor`` is not positive and finite.
        """
        return SlaDuration(self.amount * factor, self.unit)


@dataclass(frozen=True, slots=True)
class SlaTargets:
    """First-response and resolution targets for one priority and plan (spec §5.3).

    Attributes:
        first_response: First response target (FRT).
        resolution: Resolution target.
    """

    first_response: SlaDuration
    resolution: SlaDuration


def _hours(amount: int) -> SlaDuration:
    return SlaDuration(Decimal(amount), SlaUnit.hours)


def _business_days(amount: int) -> SlaDuration:
    return SlaDuration(Decimal(amount), SlaUnit.business_days)


SLA_BASE_PLAN: Final = PlanTier.business
"""Plan the §5.3 base targets are stated for (multiplier 1)."""

BASE_SLA_TARGETS: Final[Mapping[Priority, SlaTargets]] = MappingProxyType(
    {
        Priority.urgent: SlaTargets(first_response=_hours(1), resolution=_hours(8)),
        Priority.high: SlaTargets(first_response=_hours(4), resolution=_business_days(1)),
        Priority.normal: SlaTargets(first_response=_business_days(1), resolution=_business_days(3)),
        Priority.low: SlaTargets(first_response=_business_days(2), resolution=_business_days(5)),
    }
)
"""§5.3 "Base FRT" and "Base resolution target" per priority, on the business plan."""

PLAN_FRT_MULTIPLIER: Final[Mapping[PlanTier, Decimal]] = MappingProxyType(
    {
        PlanTier.free: Decimal(2),
        PlanTier.starter: Decimal("1.5"),
        PlanTier.business: Decimal(1),
        PlanTier.enterprise: Decimal("0.5"),
    }
)
"""The §3 "First-response SLA multiplier" per plan."""


def sla_targets(priority: Priority, plan: PlanTier) -> SlaTargets:
    """Return the SLA targets of a ticket (spec §5.3 with the §3 plan multiplier).

    The multiplier scales the first-response target only. Spec-ambiguous point, decided
    conservatively: §3 names it a *first-response* multiplier and §5.3 applies it to the FRT,
    so the resolution target stays at its base value on every plan; the fact sheet's
    "multiply by the plan's frt_multiplier" sits under a table holding both targets.

    Args:
        priority: Final (post-floor) priority.
        plan: Customer plan tier.

    Returns:
        The plan's first-response target and the base resolution target.
    """
    base = BASE_SLA_TARGETS[priority]
    return SlaTargets(
        first_response=base.first_response.scaled(PLAN_FRT_MULTIPLIER[plan]),
        resolution=base.resolution,
    )


PRIORITY_RANK: Final[Mapping[Priority, int]] = MappingProxyType(
    {Priority.low: 0, Priority.normal: 1, Priority.high: 2, Priority.urgent: 3}
)
"""Priority order for floor arithmetic: a higher rank is more urgent (spec §5.3)."""

_PRIORITY_BY_RANK: Final[Mapping[int, Priority]] = MappingProxyType(
    {rank: priority for priority, rank in PRIORITY_RANK.items()}
)

ORG_WIDE_MIN_USERS_AFFECTED: Final = 10
"""``user_count_affected`` at or above this makes an SSO failure org-wide (spec §5.3, A-29)."""

NEGATIVE_SENTIMENTS: Final[frozenset[Sentiment]] = frozenset(
    {Sentiment.frustrated, Sentiment.angry}
)
"""Sentiments that raise an enterprise ticket one level above the model's output (§5.3)."""


def max_priority(first: Priority, *others: Priority) -> Priority:
    """Return the most urgent of the given priorities.

    Args:
        first: A priority.
        *others: More priorities.

    Returns:
        The one with the highest rank.
    """
    return max((first, *others), key=PRIORITY_RANK.__getitem__)


def raise_priority(priority: Priority, levels: int = 1) -> Priority:
    """Return a priority raised by ``levels``, capped at ``urgent``.

    Args:
        priority: Starting priority.
        levels: Non-negative number of levels.

    Returns:
        The raised priority.

    Raises:
        ValueError: If ``levels`` is negative (a floor never lowers a priority).
    """
    if levels < 0:
        msg = f"levels must be >= 0, got {levels}"
        raise ValueError(msg)
    return _PRIORITY_BY_RANK[min(PRIORITY_RANK[priority] + levels, PRIORITY_RANK[Priority.urgent])]


@unique
class PriorityFloorRule(StrEnum):
    """The rule-N3 priority floors of spec §5.3, in spec order.

    The spec lists the floors without ids; these names exist for N3's recorded evidence.
    """

    security_report = "security_report"
    service_outage = "service_outage"
    payment_failure_suspension = "payment_failure_suspension"
    enterprise_org_wide_sso = "enterprise_org_wide_sso"
    enterprise_negative_sentiment = "enterprise_negative_sentiment"


@dataclass(frozen=True, slots=True, kw_only=True)
class PriorityFloorContext:
    """The inputs of rule N3 (spec §5.3, §7.3): enums, flags and counts, never ticket text.

    Attributes:
        model_priority: The priority to floor: the model's output, or a gold pre-floor label
            when an evaluation computes system-level priority (spec §9.12 D6-3).
        intents: Primary and secondary intents. Spec-silent point: the floors read the union,
            like the forced-review rules (§5.1), so a secondary ``service_outage`` also floors
            the ticket at ``urgent`` (raising only; this matches the E1 rules baseline).
        plan: Customer plan tier.
        sentiment: Sentiment of the latest customer message.
        suspension_language: A suspension or non-payment warning was detected in the text.
        org_wide_cue: An org-wide cue ("whole org", "nobody can log in") was detected.
        user_count_affected: Largest ``user_count_affected`` entity parsed as an integer, if any.
    """

    model_priority: Priority
    intents: frozenset[Intent]
    plan: PlanTier
    sentiment: Sentiment
    suspension_language: bool = False
    org_wide_cue: bool = False
    user_count_affected: int | None = None

    def __post_init__(self) -> None:
        """Validate the context.

        Raises:
            ValueError: If there is no intent or the user count is negative.
        """
        if not self.intents:
            msg = "intents must contain at least the primary intent"
            raise ValueError(msg)
        if self.user_count_affected is not None and self.user_count_affected < 0:
            msg = f"user_count_affected must be >= 0, got {self.user_count_affected}"
            raise ValueError(msg)

    @property
    def org_wide(self) -> bool:
        """Whether the ticket affects the whole organisation (a cue or >= 10 users, §5.3)."""
        return self.org_wide_cue or (
            self.user_count_affected is not None
            and self.user_count_affected >= ORG_WIDE_MIN_USERS_AFFECTED
        )


def applicable_floors(ctx: PriorityFloorContext) -> Mapping[PriorityFloorRule, Priority]:
    """Return every N3 floor that applies, with the minimum priority it imposes (spec §5.3).

    The enterprise sentiment floor is relative to ``ctx.model_priority`` ("at least one level
    above the model's output"), not to the result of the other floors, so the floors combine by
    maximum and are never chained.

    Args:
        ctx: Rule-N3 inputs.

    Returns:
        Read-only mapping of fired floor to its minimum priority, in spec order.
    """
    floors: dict[PriorityFloorRule, Priority] = {}
    if Intent.security_report in ctx.intents:
        floors[PriorityFloorRule.security_report] = Priority.high
    if Intent.service_outage in ctx.intents:
        floors[PriorityFloorRule.service_outage] = Priority.urgent
    if Intent.billing_payment_failure in ctx.intents and ctx.suspension_language:
        floors[PriorityFloorRule.payment_failure_suspension] = Priority.high
    enterprise = ctx.plan is PlanTier.enterprise
    if enterprise and Intent.sso_login_failure in ctx.intents and ctx.org_wide:
        floors[PriorityFloorRule.enterprise_org_wide_sso] = Priority.urgent
    if enterprise and ctx.sentiment in NEGATIVE_SENTIMENTS:
        floors[PriorityFloorRule.enterprise_negative_sentiment] = raise_priority(ctx.model_priority)
    return MappingProxyType(floors)


def priority_floor(ctx: PriorityFloorContext) -> Priority | None:
    """Return the minimum priority rule N3 requires, or ``None`` when no floor applies.

    Args:
        ctx: Rule-N3 inputs.

    Returns:
        The most urgent applicable floor, or ``None``.
    """
    floors = applicable_floors(ctx)
    return max_priority(*floors.values()) if floors else None


def apply_priority_floors(ctx: PriorityFloorContext) -> Priority:
    """Apply rule N3 once: raise the priority to every applicable floor, never lower it.

    Apply it to the model's output only: the enterprise sentiment floor is relative, so
    re-applying it to its own result would raise the priority again.

    Args:
        ctx: Rule-N3 inputs.

    Returns:
        The final priority: ``ctx.model_priority`` or the highest floor, whichever is higher.
    """
    return max_priority(ctx.model_priority, *applicable_floors(ctx).values())


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
"""Every frozen vocabulary, in export order (JSON Schema and fingerprint).

``ReasonEmitter``, ``SlaUnit`` and ``PriorityFloorRule`` label policy-table entries, not
ticket or triage fields, so they are neither exported nor part of the fingerprint.
"""
