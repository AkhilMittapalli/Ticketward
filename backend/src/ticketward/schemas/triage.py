"""Triage contracts (spec v1.1 §6.2, BR-006, BR-027, BR-028).

Two layers:

* ``TriageModelOutput`` - exactly what the SLM must emit under constrained decoding.
  Entities are ``{type, value}`` only: the model never emits spans (A-29).
* ``TriageResult`` - the system-enriched envelope that is persisted and sent to the UI.
  It adds server-computed entity spans (``ResolvedEntity``), calibrated per-field
  confidence including ``p_critical``, the policy decision and model provenance.

Nothing unvalidated reaches the UI (§6.6 step 7): the API response model is
``TriageResult`` and FastAPI response validation stays on. ``schema_version`` stays
``triage.v1``: the v1.1 bounds and the serialization flag landed before the P1 freeze.
"""

from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from ticketward.domain.taxonomy import (
    ChurnRisk,
    EntityType,
    EscalationReason,
    Intent,
    Priority,
    ProductArea,
    Queue,
    RecommendedAction,
    Sentiment,
)
from ticketward.schemas.common import ChurnSignal, ContractModel, DocKey, Prob

TRIAGE_SCHEMA_VERSION = "triage.v1"
MAX_ENTITIES = 20

PolicyDecision = Literal[
    "local_draft", "frontier_draft", "human_escalation", "abstain_request_info"
]
"""Path chosen by the deterministic policy engine (spec §7.3)."""

Provider = Literal["local_ollama", "local_vllm", "anthropic", "rules_baseline", "encoder_baseline"]
"""Producer of a model output (spec §6.2)."""

ConfidenceMethod = Literal["token_logprob", "self_consistency", "calibrated_softmax"]
"""How per-field confidence was estimated (ADR-0017)."""


class FieldConfidence(ContractModel):
    """Calibrated per-field confidence; every field is bounded to ``[0, 1]`` (A-29)."""

    intent: Prob
    priority: Prob
    sentiment: Prob
    churn_risk: Prob
    product_area: Prob
    recommended_queue: Prob
    p_critical: Prob = Field(description="P(any critical intent); feeds rule N6 (§7.3).")


class Entity(ContractModel):
    """What the model emits: type and value only, never spans (A-29).

    PII never appears raw, only as masked placeholders such as ``<EMAIL_1>`` (§5.6).
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    type: EntityType
    value: str = Field(max_length=200)


class Span(ContractModel):
    """Half-open character range ``[start, end)`` in masked subject + message coordinates."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end < self.start:
            msg = "span end must not precede its start"
            raise ValueError(msg)
        return self


class ResolvedEntity(Entity):
    """Server enrichment of a model entity (``TriageResult`` only, A-29)."""

    source_span: Span | None = Field(
        description="Exact match of value in the masked subject + message; null if absent."
    )


class TriageModelOutput(ContractModel):
    """SLM output contract (approx. 120-220 output tokens)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    intent: Intent
    secondary_intents: list[Intent] = Field(
        default_factory=list,
        max_length=2,
        description=(
            "No duplicates and never the primary intent; checked after validation "
            "(repair level 1 fixes it, §6.6)."
        ),
    )
    priority: Priority
    sentiment: Sentiment
    churn_risk: ChurnRisk
    churn_signals: list[ChurnSignal] = Field(default_factory=list, max_length=5)
    product_area: ProductArea
    entities: list[Entity] = Field(default_factory=list, max_length=MAX_ENTITIES)
    recommended_queue: Queue
    recommended_action: RecommendedAction
    customer_requested_human: bool
    information_sufficient: bool
    rationale: str = Field(
        max_length=400, description="Short rationale for agent and handoff; not chain-of-thought."
    )


class ModelMeta(ContractModel):
    """Provenance of a model output (registry version, prompt, calibration, cost)."""

    model_config = ConfigDict(protected_namespaces=())

    provider: Provider
    model_name: str = Field(max_length=200)
    model_version: str = Field(
        max_length=200,
        description=(
            "Registry version tw-triage-<base>-<method>@<semver>, e.g. "
            '"tw-triage-qwen35-2b-lora@0.1.0" (illustrative until ADR-0011).'
        ),
    )
    adapter_sha: str | None = Field(max_length=128)
    prompt_version: str = Field(max_length=64)
    taxonomy_version: str = Field(max_length=32)
    schema_version: str = Field(default=TRIAGE_SCHEMA_VERSION, max_length=32)
    policy_version: str = Field(max_length=64)
    latency_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0)
    repair_attempts: int = Field(ge=0)
    confidence_method: ConfidenceMethod
    calibrator_version: str | None = Field(
        max_length=64,
        description='E.g. "calibrator.v1" (A-04); null for uncalibrated baselines.',
    )
    calibration_fit_run_id: UUID | None = Field(description="eval_runs.id of the val fit.")
    decoding_backend: str | None = Field(
        max_length=128,
        description='E.g. "ollama-0.34.4/llama.cpp-b11081" or "vllm-0.30.x/xgrammar".',
    )
    logprobs_mode: str | None = Field(
        max_length=64, description='E.g. "ollama-raw-pre-grammar" or "vllm-raw_logprobs".'
    )


class TriageResult(TriageModelOutput):
    """System-enriched triage envelope persisted and returned to the UI."""

    # Server enrichment replaces the model's span-free entities (A-29). The narrower
    # element type is intentional; lists are invariant, hence the ignore.
    entities: list[ResolvedEntity] = Field(max_length=MAX_ENTITIES)  # type: ignore[assignment]
    ticket_id: UUID
    triage_run_id: UUID
    confidence: FieldConfidence
    citations: list[DocKey] = Field(
        description="Cited doc_keys; chunk-level detail lives in DraftResponse.citations (§8.7)."
    )
    needs_human_review: bool
    escalation_reasons: list[EscalationReason]
    policy_decision: PolicyDecision
    handoff_summary: str = Field(max_length=1200)
    matched_incident_id: str | None = Field(max_length=128)
    model: ModelMeta
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _secondary_intents_are_repaired(self) -> Self:
        # The model output may violate this (repair L1 fixes it); the envelope may not.
        secondary = self.secondary_intents
        if len(set(secondary)) != len(secondary) or self.intent in secondary:
            msg = "secondary_intents must be unique and must not repeat the primary intent"
            raise ValueError(msg)
        return self
