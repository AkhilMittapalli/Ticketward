"""Draft response contracts (spec v1.1 §6.3, BR-028).

Two layers:

* ``DraftSentence`` / ``Citation`` / ``TemplateReply`` — value objects.
* ``DraftResponse`` — the system-produced draft for agent review, with guard flags
  and a status lifecycle enforced by a model validator.

``mode="none"`` means no model-generated draft: the policy forbids drafting
(e.g. ``security_report``), and the approved acknowledgment template is attached
as the separate ``template_reply`` field (I-13).

Guard flags (A-15):

* ``claims_timing_without_source`` flags timing promises ("within 2 hours",
  "by tomorrow") that do not cite ``policy_sla``.
* Other guards (pricing, account status, refund eligibility, incident status,
  capability, URL, PII, injection echo) are evaluated by the verifier (§8.7)
  and the policy engine (§7.3).
"""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from ticketward.domain.taxonomy import DocType
from ticketward.schemas.common import ContractModel, DocKey, Prob
from ticketward.schemas.triage import ModelMeta

SentenceKind = Literal["factual", "procedural", "empathy", "question", "holding"]
"""Sentence classification used by the verifier: citation_ids must be non-empty
for ``factual`` and ``procedural`` (enforced at service layer, P6)."""

DraftMode = Literal["grounded_answer", "clarifying_questions", "holding_reply_template", "none"]
"""Draft production mode, chosen by the template-precedence table (§7.3.2)."""

DraftStatus = Literal[
    "pending_review", "approved", "edited_and_approved", "rejected", "superseded"
]
"""Draft lifecycle status.  Approved states require ``approved_by``."""

GuardFlag = Literal[
    "claims_pricing_without_source",
    "claims_account_status",
    "claims_refund_eligibility",
    "claims_incident_status_without_record",
    "claims_capability_without_source",
    "claims_timing_without_source",
    "contains_url_not_in_kb",
    "contains_pii",
    "injection_echo",
]
"""Post-verifier guard flags (spec §6.3, §8.7, A-15)."""

MAX_SENTENCES = 40
MAX_CITATIONS = 50
QUOTE_MAX_CHARS = 300
BODY_MAX_CHARS = 40_000


class DraftSentence(ContractModel):
    """One sentence of a model-generated draft (spec §6.3)."""

    text: str = Field(max_length=2_000)
    kind: SentenceKind
    citation_ids: list[str] = Field(default_factory=list, max_length=10)


class Citation(ContractModel):
    """A chunk-level citation backing one or more draft sentences (spec §6.3, §8.7).

    ``support_score`` is the NLI entailment probability of the verifier's L2 layer,
    not a retrieval score.
    """

    citation_id: str = Field(max_length=64)
    doc_id: UUID
    doc_version: int = Field(ge=1)
    chunk_id: str = Field(max_length=128)
    title: str = Field(max_length=300)
    doc_type: DocType
    url_slug: str | None = Field(default=None, max_length=300)
    quote: str = Field(max_length=QUOTE_MAX_CHARS)
    support_score: Prob


class TemplateReply(ContractModel):
    """An approved reply template attached when ``mode="none"`` (spec §6.3, I-13).

    Template keys are stable ``DocKey`` slugs (e.g. ``tpl_security_ack``),
    matching ``reply_template`` documents in the KB.
    """

    template_key: DocKey
    doc_version: int = Field(ge=1)
    body_markdown: str = Field(max_length=BODY_MAX_CHARS)


class DraftResponse(ContractModel):
    """System-produced draft for agent review (spec §6.3).

    Nothing unvalidated reaches the UI (§6.6 step 7): FastAPI response validation
    stays on for this model as well.
    """

    draft_id: UUID
    ticket_id: UUID
    triage_run_id: UUID
    mode: DraftMode
    sentences: list[DraftSentence] = Field(max_length=MAX_SENTENCES)
    body_markdown: str = Field(max_length=BODY_MAX_CHARS)
    citations: list[Citation] = Field(max_length=MAX_CITATIONS)
    template_reply: TemplateReply | None = None
    unsupported_sentence_count: int = Field(ge=0)
    generated_by: ModelMeta
    status: DraftStatus
    guard_flags: list[GuardFlag] = Field(default_factory=list)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _template_reply_iff_mode_none(self) -> Self:
        """``template_reply`` must be set when mode is ``none`` and absent otherwise."""
        if self.mode == "none" and self.template_reply is None:
            msg = "template_reply is required when mode is 'none'"
            raise ValueError(msg)
        if self.mode != "none" and self.template_reply is not None:
            msg = "template_reply must be null when mode is not 'none'"
            raise ValueError(msg)
        return self
