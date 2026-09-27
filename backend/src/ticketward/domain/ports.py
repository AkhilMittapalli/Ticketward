"""Ports: protocols the domain depends on (spec §7.1 "Key interfaces").

Adapters (``OllamaProvider``, ``AnthropicProvider``, ``Bm25sKeywordRetriever``,
``PgVectorRetriever``, ``CrossEncoderReranker``, ``SentenceTransformerEmbedder``,
``PresidioMasker``) implement these in later phases (P3-P7) and are injected via
FastAPI ``Depends``. The supporting value types are deliberately minimal and immutable.

Retrievers MUST apply approval/effective-window filtering themselves (S-09):
approved-only retrieval is not an optional filter.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel

from ticketward.domain.taxonomy import DocType, PlanTier, ProductArea

type MessageRole = Literal["system", "user", "assistant"]
type EmbeddingKind = Literal["query", "passage"]


@dataclass(frozen=True, slots=True)
class Msg:
    """One chat message sent to an LLM provider.

    Attributes:
        role: Chat role.
        content: Message text. Ticket text must already be PII-masked (§12.5).
    """

    role: MessageRole
    content: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Token accounting for one provider call.

    Attributes:
        input_tokens: Prompt tokens billed/consumed.
        output_tokens: Completion tokens produced.
    """

    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class StructuredResult:
    """Raw constrained-decoding output; parsing and repair happen downstream (§6.6).

    Attributes:
        raw_json: Unparsed model output. Never logged (it can echo masked ticket text).
        model_name: Provider model identifier actually used.
        usage: Token usage.
        latency_ms: Wall-clock latency of the call.
        field_logprobs: First-token logprob per enum field when the server exposes
            logprobs (ADR-017); ``None`` otherwise.
    """

    raw_json: str = field(repr=False)
    model_name: str
    usage: LLMUsage
    latency_ms: int
    field_logprobs: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class TextResult:
    """Free-text generation output.

    Attributes:
        text: Generated text. Never logged.
        model_name: Provider model identifier actually used.
        usage: Token usage.
        latency_ms: Wall-clock latency of the call.
    """

    text: str = field(repr=False)
    model_name: str
    usage: LLMUsage
    latency_ms: int


@dataclass(frozen=True, slots=True)
class RetrievalFilters:
    """Metadata filters applied before scoring (spec §8.6).

    Attributes:
        doc_types: Restrict to these document types (``None`` = all).
        product_areas: Soft-boost/restrict by product area (``None`` = all).
        plan_tier: Customer plan for ``plans_applicable`` filtering.
        include_stale: Whether stale (review-overdue) chunks may be returned with a penalty.
    """

    doc_types: frozenset[DocType] | None = None
    product_areas: frozenset[ProductArea] | None = None
    plan_tier: PlanTier | None = None
    include_stale: bool = True


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A retrieved knowledge-base chunk with its score.

    Attributes:
        chunk_id: Stable chunk id ``{doc_key}#c{n}`` (spec §8.3).
        doc_key: Stable document slug, e.g. ``kb_sso_redirect_loop``.
        doc_version: Approved document version the chunk belongs to.
        doc_type: Document type.
        title: Document title.
        heading_path: Heading breadcrumb within the document.
        content: Chunk text (approved KB content, not ticket text).
        score: Retriever/reranker score; semantics depend on the producing stage.
        is_stale: Whether the document is past ``review_due_at`` (spec §8.8).
    """

    chunk_id: str
    doc_key: str
    doc_version: int
    doc_type: DocType
    title: str
    heading_path: str
    content: str = field(repr=False)
    score: float
    is_stale: bool = False


@dataclass(frozen=True, slots=True)
class MaskResult:
    """PII masking output (spec §12.5).

    Attributes:
        masked_text: Text with typed, indexed placeholders (``<EMAIL_1>`` ...).
        mapping: Placeholder -> original value. Server-side only, stored encrypted,
            never sent to models, logs or traces; excluded from ``repr``.
        entity_counts: Count of masked entities per entity label.
    """

    masked_text: str = field(repr=False)
    mapping: Mapping[str, str] = field(repr=False)
    entity_counts: Mapping[str, int]


class LLMProvider(Protocol):
    """Local or frontier language-model provider (ADR-015)."""

    name: str

    async def generate_structured(
        self,
        *,
        messages: Sequence[Msg],
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int,
        timeout_s: float,
        request_id: str,
    ) -> StructuredResult:
        """Generate JSON constrained to ``schema``'s JSON Schema.

        Args:
            messages: Chat messages (masked).
            schema: Pydantic model whose JSON Schema constrains decoding.
            temperature: Sampling temperature (0 for triage).
            max_tokens: Output token cap.
            timeout_s: Hard timeout for the call.
            request_id: Correlation id propagated to provider logs/traces.

        Returns:
            The raw structured output and usage.
        """
        ...

    async def generate_text(
        self,
        *,
        messages: Sequence[Msg],
        max_tokens: int,
        temperature: float,
        timeout_s: float,
        request_id: str,
    ) -> TextResult:
        """Generate free text.

        Args:
            messages: Chat messages (masked).
            max_tokens: Output token cap.
            temperature: Sampling temperature.
            timeout_s: Hard timeout for the call.
            request_id: Correlation id.

        Returns:
            The generated text and usage.
        """
        ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Estimate the USD cost of a call from token counts (dated price table)."""
        ...


class KeywordRetriever(Protocol):
    """BM25-style keyword retrieval over approved chunks (ADR-007)."""

    async def search(self, query: str, k: int, filters: RetrievalFilters) -> list[ScoredChunk]:
        """Return the top ``k`` approved chunks for ``query``."""
        ...


class VectorRetriever(Protocol):
    """Dense retrieval over approved chunk embeddings (ADR-005, ADR-008)."""

    async def search(
        self, embedding: Sequence[float], k: int, filters: RetrievalFilters
    ) -> list[ScoredChunk]:
        """Return the top ``k`` approved chunks nearest to ``embedding``."""
        ...


class Reranker(Protocol):
    """Cross-encoder reranker (ADR-009)."""

    async def rerank(
        self, query: str, chunks: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        """Rescore ``chunks`` against ``query`` and return the best ``top_n``."""
        ...


class Embedder(Protocol):
    """Text embedding model (ADR-008)."""

    async def embed(self, texts: Sequence[str], kind: EmbeddingKind) -> list[list[float]]:
        """Embed ``texts`` as queries or passages (model-card prefixes applied internally)."""
        ...


class PIIMasker(Protocol):
    """PII detector/masker run before any model call, log or trace (ADR-019)."""

    def mask(self, text: str) -> MaskResult:
        """Mask PII in ``text`` and return the masked text plus a reversible map."""
        ...
