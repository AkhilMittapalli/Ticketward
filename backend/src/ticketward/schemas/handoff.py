"""Handoff brief contracts (spec v1.1 §6.4, BR-020).

Three variants share a base:

* ``HandoffBase`` — common fields for every escalation target.
* ``CSMHandoff`` — adds sentiment trajectory, issue history, churn signals and
  a recommended follow-up for the customer-success manager.
* ``EngineeringHandoff`` — adds reproduction steps, error codes, environment,
  customer impact and a severity suggestion.

The generic variant (billing, security_privacy, tier_2) uses ``HandoffBase``
directly; the ``variant`` field distinguishes.

**Completeness rule (T-HANDOFF-completeness):** every entity extracted in triage,
every citation shown to the agent, and every escalation reason must appear in the
brief.  The handoff generator is deterministic assembly plus an SLM-written
``one_line_summary`` / ``customer_problem``, so fields cannot be silently dropped.
"""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from ticketward.domain.taxonomy import (
    ChurnRisk,
    EscalationReason,
    Intent,
    PlanTier,
    Priority,
    Sentiment,
)
from ticketward.schemas.common import ContractModel
from ticketward.schemas.triage import Entity

HandoffTarget = Literal["csm", "engineering", "billing", "security_privacy", "tier_2"]
"""Escalation target queue / role (spec §6.4)."""

HandoffVariant = Literal["csm", "engineering", "generic"]
"""Brief variant: specialized for CSM or engineering, generic otherwise."""

RecommendedFollowUp = Literal[
    "exec_call", "csm_call_48h", "email_check_in", "billing_goodwill_review", "none"
]
"""CSM follow-up action (spec §6.4)."""

SeveritySuggestion = Literal["sev1", "sev2", "sev3", "sev4"]
"""Engineering severity level (spec §6.4)."""

SUMMARY_MAX_CHARS = 200
STEPS_MAX = 20
ARTICLES_MAX = 20
OPEN_QUESTIONS_MAX = 10
ENTITIES_MAX = 20
REASONS_MAX = 10
CHURN_SIGNALS_MAX = 10
ISSUE_HISTORY_MAX = 5
REPRO_STEPS_MAX = 20
ERROR_CODES_MAX = 20


class TicketContextRef(ContractModel):
    """Pointer to the originating ticket without echoing its text."""

    ticket_id: UUID
    message_count: int = Field(ge=0)
    first_received_at: AwareDatetime


class SentimentSnapshot(ContractModel):
    """A point-in-time sentiment reading (spec §6.4, CSM variant)."""

    at: AwareDatetime
    sentiment: Sentiment


class IssueHistoryEntry(ContractModel):
    """A recent ticket for the same account (spec §6.4, last 5 / 90 days)."""

    ticket_id: UUID
    intent: Intent
    status: str = Field(max_length=64)
    created_at: AwareDatetime


class EnvironmentInfo(ContractModel):
    """Client environment reported with a bug or outage (spec §6.4)."""

    browser: str | None = Field(default=None, max_length=200)
    os: str | None = Field(default=None, max_length=200)
    app_version: str | None = Field(default=None, max_length=50)
    platform: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=50)


class CustomerImpact(ContractModel):
    """Scope of customer impact for engineering triage (spec §6.4)."""

    users_affected: int | None = Field(default=None, ge=0)
    workspaces_affected: int | None = Field(default=None, ge=0)
    business_impact: str = Field(max_length=1_000)


class HandoffBase(ContractModel):
    """Common handoff brief fields (spec §6.4).

    The generic variant (billing, security_privacy, tier_2) uses this model
    directly.  CSM and engineering variants extend it.
    """

    handoff_id: UUID
    ticket_id: UUID
    target: HandoffTarget
    variant: HandoffVariant
    one_line_summary: str = Field(max_length=SUMMARY_MAX_CHARS)
    customer_problem: str = Field(max_length=2_000)
    customer_goal: str = Field(max_length=1_000)
    account_tier: PlanTier
    arr_band: str | None = Field(default=None, max_length=20)
    intent: Intent
    priority: Priority
    sentiment: Sentiment
    churn_risk: ChurnRisk
    entities: list[Entity] = Field(max_length=ENTITIES_MAX)
    steps_already_attempted: list[str] = Field(max_length=STEPS_MAX)
    articles_already_checked: list[str] = Field(max_length=ARTICLES_MAX)
    rationale: str = Field(max_length=2_000)
    escalation_reasons: list[EscalationReason] = Field(min_length=1, max_length=REASONS_MAX)
    open_questions: list[str] = Field(default_factory=list, max_length=OPEN_QUESTIONS_MAX)
    customer_facing_expectation: str = Field(max_length=2_000)
    ticket_context_ref: TicketContextRef
    edited_by: UUID | None = None
    version: int = Field(ge=1)


class CSMHandoff(HandoffBase):
    """Customer-success manager handoff (spec §6.4)."""

    variant: Literal["csm"]
    sentiment_trajectory: list[SentimentSnapshot] = Field(max_length=20)
    issue_history: list[IssueHistoryEntry] = Field(max_length=ISSUE_HISTORY_MAX)
    churn_signals: list[str] = Field(max_length=CHURN_SIGNALS_MAX)
    recommended_follow_up: RecommendedFollowUp

    @model_validator(mode="after")
    def _target_is_csm_compatible(self) -> Self:
        if self.target != "csm":
            msg = "CSMHandoff target must be 'csm'"
            raise ValueError(msg)
        return self


class EngineeringHandoff(HandoffBase):
    """Engineering escalation handoff (spec §6.4)."""

    variant: Literal["engineering"]
    reproduction_steps: list[str] = Field(default_factory=list, max_length=REPRO_STEPS_MAX)
    expected_behavior: str | None = Field(default=None, max_length=2_000)
    actual_behavior: str | None = Field(default=None, max_length=2_000)
    error_codes: list[str] = Field(default_factory=list, max_length=ERROR_CODES_MAX)
    environment: EnvironmentInfo
    customer_impact: CustomerImpact
    first_seen_at: AwareDatetime | None = None
    linked_incident_id: str | None = Field(default=None, max_length=128)
    severity_suggestion: SeveritySuggestion

    @model_validator(mode="after")
    def _target_is_engineering_compatible(self) -> Self:
        if self.target != "engineering":
            msg = "EngineeringHandoff target must be 'engineering'"
            raise ValueError(msg)
        return self
