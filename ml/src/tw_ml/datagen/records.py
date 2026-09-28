"""Dataset record models: ticket, labels, sampled cell and full provenance (spec §6.1, §6.2, §9.1).

* :class:`TicketPayload` mirrors the ``TicketCreate`` subset a training example needs.
* :class:`TriageLabels` mirrors ``TriageModelOutput`` field for field, in the same order (the
  decoding-schema / training-target key order). ``tests/test_taxonomy.py`` compares both with
  the exported JSON Schemas.
* :class:`Provenance` carries every §9.1 step 8 field plus the v1.1 additions, and enforces
  T-DATA-provenance: allowed generator families per split and no Anthropic-produced record
  anywhere (A-01, S-12).

All models forbid unknown fields and hide input values from validation errors, so ticket text
never leaks into logs or tracebacks.
"""

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from tw_ml.datagen.taxonomy import (
    ChannelValue,
    ChurnRiskValue,
    EntityTypeValue,
    IntentValue,
    PlanTierValue,
    PriorityValue,
    ProductAreaValue,
    QueueValue,
    RecommendedActionValue,
    SentimentValue,
    load_taxonomy,
)
from tw_ml.datagen.text import content_sha256, join_customer_text

Split = Literal["train", "val", "test_synth", "test_hard", "test_ood", "e2e_scenarios"]
TRAINABLE_SPLITS: Final[tuple[Split, ...]] = ("train", "val")
PROTECTED_SPLITS: Final[tuple[Split, ...]] = (
    "test_synth",
    "test_hard",
    "test_ood",
    "e2e_scenarios",
)
SPLIT_CODES: Final[Mapping[Split, str]] = {
    "train": "tr",
    "val": "va",
    "test_synth": "ts",
    "test_hard": "th",
    "test_ood": "to",
    "e2e_scenarios": "te",
}

GeneratorFamily = Literal["openai_gpt_oss", "deepseek", "mistral", "human", "public_bitext"]
LabelSource = Literal["generator_proposed", "human_verified", "human_written", "public_mapped"]
LabelBasis = Literal["llm_proposal", "scenario_spec", "human", "bitext_mapping"]
PromptFamily = Literal["P-A", "P-B"]
MappingTier = Literal["T1", "T2", "probe"]
Probe = Literal["P-H", "P-N"]

ALLOWED_FAMILIES: Final[Mapping[Split, frozenset[str]]] = {
    "train": frozenset({"openai_gpt_oss", "human"}),
    "val": frozenset({"openai_gpt_oss", "human"}),
    "test_synth": frozenset({"deepseek", "mistral"}),  # D-07: DeepSeek-V3.2; Mistral = alternative
    "test_hard": frozenset({"human"}),
    "test_ood": frozenset({"public_bitext"}),
    "e2e_scenarios": frozenset({"deepseek", "mistral", "human"}),
}
"""T-DATA-provenance (spec §9.1 step 8, S-12)."""

LLM_FAMILIES: Final[frozenset[str]] = frozenset({"openai_gpt_oss", "deepseek", "mistral"})
"""Families whose records come from a prompted model (they need a prompt family)."""

FORBIDDEN_VENDOR_MARKERS: Final[tuple[str, ...]] = ("anthropic", "claude")
"""A-01: no Anthropic-produced record may enter data/ (checked on every free-text field)."""

RECORD_ID_PATTERN: Final = r"^[a-z]{2}_[a-z0-9_]{3,64}$"
QUANTIZATION_PATTERN: Final = r"^[a-z0-9][a-z0-9_.-]{0,31}$"  # fp4, fp8, bf16, int4-awq ...
SHA256_PATTERN: Final = r"^[0-9a-f]{64}$"
Sha256 = Annotated[str, StringConstraints(pattern=SHA256_PATTERN)]
ChurnSignal = Annotated[str, StringConstraints(max_length=200)]


class RecordModel(BaseModel):
    """Base for every data model: unknown fields rejected, inputs hidden from errors."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)


# --------------------------------------------------------------------------- ticket


class PreviousMessage(RecordModel):
    """A prior message in the ticket thread (``TicketCreate.previous_messages``)."""

    author: Literal["customer", "agent", "system"]
    body: str = Field(max_length=20_000)
    sent_at: AwareDatetime


class AccountMetadata(RecordModel):
    """Synthetic CRM metadata (``TicketCreate.account``)."""

    account_id: str = Field(pattern=r"^acct_[A-Za-z0-9]{4,32}$")
    company_name: str | None = Field(default=None, max_length=200)
    arr_band: Literal["<10k", "10k-50k", "50k-250k", ">250k"] | None = None
    region: Literal["us", "eu", "apac"] | None = None
    seats: int | None = Field(default=None, ge=1, le=1_000_000)


class ProductMetadata(RecordModel):
    """Optional product context (``TicketCreate.product``)."""

    product_area_hint: ProductAreaValue | None = None
    app_version: str | None = Field(default=None, max_length=50)
    platform: Literal["web", "ios", "android", "desktop", "api"] | None = None


class TicketPayload(RecordModel):
    """The ``TicketCreate`` subset used for training and evaluation (spec §6.1).

    ``customer_email`` is intentionally absent: generated data never carries e-mail
    addresses (PII appears only as ``<EMAIL_n>`` placeholders).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str | None = Field(default=None, max_length=128)
    customer_tier: PlanTierValue
    channel: ChannelValue
    subject: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=20_000)
    previous_messages: tuple[PreviousMessage, ...] = Field(default=(), max_length=50)
    account: AccountMetadata | None = None
    product: ProductMetadata | None = None
    received_at: AwareDatetime | None = None

    def customer_text(self) -> str:
        """Return ``customer_text``: subject, message and customer-authored history.

        Returns:
            The text every leakage check compares (ERPROT leakage D1).
        """
        prior = (m.body for m in self.previous_messages if m.author == "customer")
        return join_customer_text(self.subject, self.message, prior)

    def full_text(self) -> str:
        """Return subject, message and every prior message body (what the model reads).

        Returns:
            Newline-joined text used for literal-entity checks.
        """
        return "\n".join([self.subject, self.message, *(m.body for m in self.previous_messages)])


# --------------------------------------------------------------------------- labels


class EntityLabel(RecordModel):
    """``Entity``: type and value only, never spans (A-29)."""

    type: EntityTypeValue
    value: str = Field(max_length=200)


class TriageLabels(RecordModel):
    """Labels mirroring ``TriageModelOutput`` (same fields, same order, same bounds).

    These are the generator's proposal (P-A), the scenario-spec gold (P-B), or the owner's
    labels (hard set). ``label_source`` in the provenance says which, and whether a human has
    verified them.
    """

    intent: IntentValue
    secondary_intents: tuple[IntentValue, ...] = Field(default=(), max_length=2)
    priority: PriorityValue
    sentiment: SentimentValue
    churn_risk: ChurnRiskValue
    churn_signals: tuple[ChurnSignal, ...] = Field(default=(), max_length=5)
    product_area: ProductAreaValue
    entities: tuple[EntityLabel, ...] = Field(default=(), max_length=20)
    recommended_queue: QueueValue
    recommended_action: RecommendedActionValue
    customer_requested_human: bool
    information_sufficient: bool
    rationale: str = Field(max_length=400)


# --------------------------------------------------------------------------- cell


class GenerationCell(RecordModel):
    """One sampled generation-matrix cell: everything the prompt card states (spec §9.1.1).

    The cell is stored with the record so the rule-checker can compare the labels with what
    the generator was asked to write (R1, R6, R7, card checks) without the plan file.
    """

    cell_id: str
    split: Split
    seq: int = Field(ge=0)
    intent: IntentValue
    secondary_intents: tuple[IntentValue, ...] = Field(default=(), max_length=2)
    secondary_order: Literal["primary_first", "secondary_first", "interleaved"] | None = None
    difficulty: str
    product_area: ProductAreaValue
    plan: PlanTierValue
    channel: ChannelValue
    sentiment: SentimentValue
    style: str
    length_bucket: str
    target_words: int = Field(ge=1)
    subject_style: str
    human_request: Literal["none", "direct", "indirect"]
    churn_cue: Literal[
        "none",
        "vague_alternatives",
        "repeated_contact",
        "explicit_cancel",
        "competitor",
        "ultimatum",
    ]
    competitor: str | None = None
    priority_hint: PriorityValue
    information_sufficient: bool
    lexical_avoid: bool = False
    banned_words: tuple[str, ...] = ()
    greeting_allowed: bool = False
    noise: bool = False
    pii_placeholders: tuple[str, ...] = ()
    legal_threat: bool = False
    injection: str | None = None
    entities: tuple[EntityLabel, ...] = ()
    display_values: tuple[str, ...] = ()
    omissions: tuple[str, ...] = ()
    history_len: int = Field(default=0, ge=0, le=10)
    feature_name: str | None = None
    scenario_type: str | None = None
    persona_id: str
    company_id: str
    template_id: str
    scenario_seed: int = Field(ge=0)
    received_at: AwareDatetime


# --------------------------------------------------------------------------- generator side outputs


class SelfCheck(RecordModel):
    """The P-A generator's own note on whether it satisfied the card (never trusted alone)."""

    card_satisfied: bool
    note: str = Field(default="", max_length=600)


class ScenarioFacts(RecordModel):
    """P-B stage-1 output: the neutral case timeline behind a test ticket."""

    timeline: tuple[str, ...] = Field(min_length=1, max_length=12)
    customer_goal: str = Field(min_length=1, max_length=600)
    facts_customer_knows: tuple[str, ...] = Field(default=(), max_length=20)
    facts_customer_does_not_know: tuple[str, ...] = Field(default=(), max_length=20)


# --------------------------------------------------------------------------- provenance


class BitextRef(RecordModel):
    """Row pointer into a pinned Bitext dataset (test_ood only; A-13)."""

    dataset: str
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    row: int = Field(ge=0)
    intent: str
    category: str
    tags: str = ""
    fill_seed: int = Field(ge=0)


class Provenance(RecordModel):
    """Full record provenance (spec §9.1 step 8, v1.1 A-01/A-11/A-13).

    ``generator_model`` is the open-weights model id; ``api_model_id`` is the hosted API's id for
    it (they differ on some hosts, e.g. Mistral's ``mistral-large-3-25-12``).
    ``generator_quantization`` is the precision the host served the model in (``fp4`` for
    DeepSeek-V3.2 on DeepInfra), taken from the host profile; ``None`` when not stated.
    """

    record_id: str = Field(pattern=RECORD_ID_PATTERN)
    split: Split
    generator_family: GeneratorFamily
    generator_model: str = Field(min_length=1, max_length=200)
    api_model_id: str | None = Field(default=None, max_length=200)
    generator_quantization: str | None = Field(default=None, pattern=QUANTIZATION_PATTERN)
    provider: str = Field(min_length=1, max_length=100)
    generator_endpoint: str | None = Field(default=None, max_length=400)
    prompt_family: PromptFamily | None = None
    prompt_version: str | None = Field(default=None, max_length=64)
    template_id: str | None = Field(default=None, max_length=64)
    cell_id: str | None = Field(default=None, max_length=64)
    scenario_seed: int | None = Field(default=None, ge=0)
    persona_id: str | None = Field(default=None, max_length=64)
    company_id: str | None = Field(default=None, max_length=64)
    noise_ops: tuple[str, ...] = ()
    seed: int = Field(ge=0)
    created_at: AwareDatetime
    label_source: LabelSource
    label_basis: LabelBasis
    taxonomy_version: str
    content_sha256: Sha256
    terms_snapshot_id: str | None = Field(default=None, max_length=200)
    llm_assisted: bool | None = None
    mapping_tier: MappingTier | None = None
    probe: Probe | None = None
    bitext: BitextRef | None = None
    reviewed_by: tuple[str, ...] = ()
    review_round: int = Field(default=0, ge=0)
    label_notes: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def _policy(self) -> Self:
        problems = provenance_violations(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def provenance_violations(prov: Provenance) -> list[str]:
    """List every T-DATA-provenance violation of one provenance block.

    Args:
        prov: Provenance to check.

    Returns:
        Human-readable problems; empty when the provenance is valid.
    """
    problems: list[str] = []
    if prov.generator_family not in ALLOWED_FAMILIES[prov.split]:
        problems.append(f"generator_family {prov.generator_family} not allowed in {prov.split}")
    vendor_fields = (
        prov.generator_model,
        prov.api_model_id,
        prov.provider,
        prov.generator_endpoint,
    )
    if any(_mentions_forbidden_vendor(value) for value in vendor_fields if value):
        problems.append("Anthropic-produced records are forbidden in data/ (A-01)")
    if prov.taxonomy_version != load_taxonomy().version:
        problems.append("taxonomy_version does not match schemas/json/taxonomy.schema.json")
    if prov.split == "test_hard" and prov.llm_assisted is not False:
        problems.append("test_hard records need the attestation llm_assisted=false")
    if prov.split == "test_ood" and (prov.bitext is None or prov.mapping_tier is None):
        problems.append("test_ood records need a bitext row pointer and a mapping_tier")
    if prov.generator_family in LLM_FAMILIES and prov.prompt_family is None:
        problems.append("generated records need a prompt_family")
    if prov.generator_quantization is not None and prov.generator_family not in LLM_FAMILIES:
        problems.append("generator_quantization is recorded only for model-generated records")
    if prov.label_source == "human_verified" and not prov.reviewed_by:
        problems.append("human_verified labels need reviewed_by")
    return problems


def _mentions_forbidden_vendor(value: str) -> bool:
    lowered = value.lower()
    return any(re.search(rf"\b{marker}", lowered) for marker in FORBIDDEN_VENDOR_MARKERS)


# --------------------------------------------------------------------------- records


class DatasetRecord(RecordModel):
    """A labelled ticket with provenance (train, val, test_synth, test_hard, e2e)."""

    ticket: TicketPayload
    labels: TriageLabels
    provenance: Provenance
    cell: GenerationCell | None = None
    self_check: SelfCheck | None = None
    scenario: ScenarioFacts | None = None

    @property
    def record_id(self) -> str:
        """The record id (from the provenance)."""
        return self.provenance.record_id

    @property
    def split(self) -> Split:
        """The split (from the provenance)."""
        return self.provenance.split

    @model_validator(mode="after")
    def _content_hash_matches(self) -> Self:
        if self.provenance.content_sha256 != content_sha256(self.ticket.customer_text()):
            msg = "provenance.content_sha256 does not match the normalized customer_text"
            raise ValueError(msg)
        if self.cell is not None and self.cell.split != self.provenance.split:
            msg = "cell.split differs from provenance.split"
            raise ValueError(msg)
        return self


class OODGold(RecordModel):
    """Gold for a mapped Bitext item: intent plus the probe fields (A-13)."""

    intent: IntentValue
    customer_requested_human: bool | None = None
    not_intent: IntentValue | None = None


class OODRecord(RecordModel):
    """A materialized test_ood item (never committed: CDLA-Sharing-1.0 text)."""

    ticket: TicketPayload
    gold: OODGold
    provenance: Provenance

    @property
    def record_id(self) -> str:
        """The record id (from the provenance)."""
        return self.provenance.record_id

    @model_validator(mode="after")
    def _content_hash_matches(self) -> Self:
        if self.provenance.content_sha256 != content_sha256(self.ticket.customer_text()):
            msg = "provenance.content_sha256 does not match the normalized customer_text"
            raise ValueError(msg)
        return self


def utc_iso(moment: datetime) -> str:
    """Format an aware datetime as ISO 8601 (seconds precision).

    Args:
        moment: Timezone-aware datetime.

    Returns:
        ISO 8601 string with offset.

    Raises:
        ValueError: If ``moment`` is naive.
    """
    if moment.tzinfo is None:
        msg = "naive datetimes are not allowed (DTZ)"
        raise ValueError(msg)
    return moment.isoformat(timespec="seconds")
