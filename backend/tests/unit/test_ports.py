"""Ports: value objects never leak content via repr, and the protocols are implementable."""

import dataclasses
from collections.abc import Sequence
from decimal import Decimal

import pytest
from pydantic import BaseModel

from ticketward.domain.ports import (
    Embedder,
    EmbeddingKind,
    KeywordRetriever,
    LLMProvider,
    LLMUsage,
    MaskResult,
    Msg,
    PIIMasker,
    Reranker,
    RetrievalFilters,
    ScoredChunk,
    StructuredResult,
    TextResult,
    VectorRetriever,
)
from ticketward.domain.taxonomy import DocType, PlanTier
from ticketward.schemas.triage import TriageModelOutput

CHUNK = ScoredChunk(
    chunk_id="kb_sso_redirect_loop#c1",
    doc_key="kb_sso_redirect_loop",
    doc_version=3,
    doc_type=DocType.help_article,
    title="SSO redirect loop",
    heading_path="Troubleshooting > Okta",
    content="Clear the IdP session cookie and retry.",
    score=0.8,
)


def test_sensitive_fields_are_excluded_from_repr() -> None:
    mask = MaskResult(
        masked_text="Hi <PERSON_1>, card <CARD_LAST4_1>",
        mapping={"<PERSON_1>": "Alice Example"},
        entity_counts={"PERSON": 1},
    )
    message = Msg(role="user", content="raw masked ticket text")
    structured = StructuredResult(
        raw_json='{"intent": "refund_request"}',
        model_name="tw-triage",
        usage=LLMUsage(input_tokens=10, output_tokens=5),
        latency_ms=12,
    )
    text = TextResult(
        text="draft body", model_name="tw-triage", usage=structured.usage, latency_ms=9
    )
    assert "Alice" not in repr(mask)
    assert "PERSON_1" not in repr(mask)
    assert "ticket text" not in repr(message)
    assert "refund_request" not in repr(structured)
    assert "draft body" not in repr(text)
    assert "Clear the IdP" not in repr(CHUNK)


def test_value_objects_are_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        CHUNK.score = 1.0  # type: ignore[misc]


def test_retrieval_filters_default_to_everything_approved() -> None:
    filters = RetrievalFilters(plan_tier=PlanTier.business)
    assert filters.doc_types is None
    assert filters.include_stale is True


class _FakeProvider:
    name = "fake"

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
        return StructuredResult(
            raw_json=f'{{"schema": "{schema.__name__}"}}',
            model_name=self.name,
            usage=LLMUsage(input_tokens=len(messages), output_tokens=max_tokens),
            latency_ms=0,
        )

    async def generate_text(
        self,
        *,
        messages: Sequence[Msg],
        max_tokens: int,
        temperature: float,
        timeout_s: float,
        request_id: str,
    ) -> TextResult:
        return TextResult(
            text="ok", model_name=self.name, usage=LLMUsage(len(messages), 1), latency_ms=0
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return Decimal(0)


class _FakeRetriever:
    async def search(self, query: str, k: int, filters: RetrievalFilters) -> list[ScoredChunk]:
        return [CHUNK][:k]


class _FakeVectorRetriever:
    async def search(
        self, embedding: Sequence[float], k: int, filters: RetrievalFilters
    ) -> list[ScoredChunk]:
        return [CHUNK][:k]


class _FakeReranker:
    async def rerank(
        self, query: str, chunks: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        return list(chunks)[:top_n]


class _FakeEmbedder:
    async def embed(self, texts: Sequence[str], kind: EmbeddingKind) -> list[list[float]]:
        return [[0.0] * 384 for _ in texts]


class _FakeMasker:
    def mask(self, text: str) -> MaskResult:
        return MaskResult(masked_text=text, mapping={}, entity_counts={})


async def test_protocols_are_structurally_implementable() -> None:
    provider: LLMProvider = _FakeProvider()
    keyword: KeywordRetriever = _FakeRetriever()
    vector: VectorRetriever = _FakeVectorRetriever()
    reranker: Reranker = _FakeReranker()
    embedder: Embedder = _FakeEmbedder()
    masker: PIIMasker = _FakeMasker()

    structured = await provider.generate_structured(
        messages=[Msg(role="system", content="triage")],
        schema=TriageModelOutput,
        temperature=0.0,
        max_tokens=220,
        timeout_s=15.0,
        request_id="req-ports-0001",
    )
    assert "TriageModelOutput" in structured.raw_json
    text = await provider.generate_text(
        messages=[], max_tokens=10, temperature=0.0, timeout_s=1.0, request_id="req-ports-0002"
    )
    assert text.text == "ok"
    assert provider.estimate_cost(100, 50) == Decimal(0)
    filters = RetrievalFilters()
    assert await keyword.search("sso loop", 5, filters) == [CHUNK]
    assert await vector.search([0.1] * 384, 1, filters) == [CHUNK]
    assert await reranker.rerank("sso loop", [CHUNK, CHUNK], 1) == [CHUNK]
    assert len((await embedder.embed(["a", "b"], "passage"))[1]) == 384
    assert masker.mask("hello").masked_text == "hello"
