---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §8.3, §8.4, §9.3, §12.3; research embedding-model-choice, hybrid-retrieval
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0008: bge-small-en-v1.5 embeddings (384-d) with an HNSW index

> **Amended in spec v1.1 (2026-09-27; change record A-14, A-12).**
> * The model is pinned by HF revision (`TW_EMBEDDING_REVISION`), loaded with `trust_remote_code=False`, with
>   normalized embeddings.
> * **The query prompt is configured explicitly**, because sentence-transformers does not apply bge-small's
>   instruction automatically: `prompts={"query": "Represent this sentence for searching relevant passages: "}`.
>   Passages take no instruction.
> * **Startup asserts `dim == 384` and `kb_chunks.embedding_model == "<id>@<revision>"`.** Mixing vector spaces is
>   silent corruption, so the process refuses to serve on a mismatch.
> * **P5 bake-off with a switch rule** on `qrels_dev`. A 768-d winner is migrated additively.
> * The **leakage check keeps its own pinned bge-small**, independent of the retrieval embedder (A-12). The v1.0
>   consequence "changing the embedder forces a leakage re-calibration" no longer holds.

## Context and Problem Statement

Dense retrieval embeds about 2,000 KB chunks (target 350, max 512 tokens, each prefixed with
`"{title} > {heading_path}"`, §8.3) and one query per ticket. It runs on CPU in the API process (manual search) and in
the worker (pipeline), next to Ollama, the reranker and the NLI verifier. The retrieval budget is 1.5 s (§7.7), and
M-08 targets retrieval P95 ≤ 600 ms. Content is English only (NG-07).

Security constraints (§12.3, §12.11):
* no egress beyond the allow-list;
* model artifacts pinned by revision, safetensors only, no remote code;
* queries are built from masked text, but they are still customer content.

Which embedding model and ANN index should v1 use, and how is a later switch governed?

## Decision Drivers

* Retrieval quality on our qrels (M-05 Recall@5 ≥ 0.90, Recall@1 ≥ 0.65 on `qrels_test`).
* CPU latency and memory next to the other in-process models.
* No third-party egress of customer-derived text (LLM02:2026).
* Supply-chain hygiene: pinned revision, safetensors, no remote code, permissive licence (LLM04:2026).
* Protection against silent vector-space mixing after a model or revision change.

## Considered Options

1. `BAAI/bge-small-en-v1.5` (384-d) with pgvector HNSW; P5 bake-off with an explicit switch rule (chosen)
2. `BAAI/bge-base-en-v1.5` (768-d)
3. 384-d drop-ins: `ibm-granite/granite-embedding-small-english-r2`, `Snowflake/snowflake-arctic-embed-s`
4. 768-d challengers: `MongoDB/mdbr-leaf-ir`, `Alibaba-NLP/gte-modernbert-base`
5. `nomic-ai/nomic-embed-text-v1.5`
6. OpenAI embeddings API

## Decision Outcome

Chosen option: "bge-small-en-v1.5 + HNSW, with a P5 bake-off switch rule", because it is a small, permissively
licensed (MIT), CPU-friendly English embedder, and its 384-d vectors keep the index small. Candidates can still
displace it through a measured, pre-agreed rule.

**Switch rule (spec §8.4).** On `qrels_dev`, the decision metric is the full hybrid pipeline (A4). A challenger is
adopted only if all of these hold:
* dev A4 Recall@5 improves by **≥ +2.0 points**, with a CI that excludes 0;
* no other metric regresses by > 1 point;
* query-embedding P95 ≤ 50 ms;
* the licence is Apache or MIT;
* no remote code is needed.

A 768-d winner is migrated **additively**: add `embedding_v2 vector(768)` with its own partial HNSW index, backfill,
switch reads, and drop the old column one release later.

Excluded from the bake-off:
* EmbeddingGemma (Gemma Terms, gated);
* Qwen3-Embedding-0.6B (too heavy for the CPU default);
* nomic-embed-text-v1.5, unless it loads without remote code.

**Chunk-length rule (proposed):** `token_count` is measured with the embedder's tokenizer, header included, and must
be ≤ 512. The embedder truncates silently past its maximum.

**Verify at build (research `embedding-model-choice`):** the revision SHA to pin and the query prompt string.

### Consequences

* Good, because the corpus embeds in seconds on CPU, and query embedding takes milliseconds.
* Good, because a revision change or model swap cannot silently corrupt retrieval. Startup refuses a mismatched
  `embedding_model`, and a re-embed runs through `scripts/reindex.py` plus a migration.
* Good, because the switch rule prevents "benchmark shopping". Adoption needs a pre-set margin on dev data, and
  reporting stays on `qrels_test`.
* Bad, because a small model may trail larger ones on hard paraphrases. BM25 and the reranker compensate, and the
  bake-off measures the gap.
* Neutral, because HNSW isn't strictly necessary at 2k rows. It is used so the design scales, with the P5 HNSW-vs-exact
  recall check (ADR-0005).

### Confirmation

* Unit test: query and passage vectors differ for the same text (the explicit prompt is applied).
* Startup and readiness assertion: `dim == 384` and `embedding_model == "<id>@<revision>"` for all retrievable
  chunks. `/api/v1/health/ready` reports the embedder, and a mismatch means not ready.
* P5 bake-off report on `qrels_dev`, with the switch-rule decision recorded. M-05 on `qrels_test`.
* Semgrep: no `trust_remote_code=True`. Loader code uses the pinned `revision=` and safetensors.
* (proposed) Chunker unit test: `token_count` (embedder tokenizer, header included) ≤ 512 for every seed chunk.
* M-08 retrieval stage timing (`make bench-latency`).

## Pros and Cons of the Options

### bge-small-en-v1.5 (384-d)

* Good, because it is fast on CPU, small, strong on English retrieval, MIT-licensed, and plain BERT (no remote code).
* Bad, because its 512-token input limit and smaller capacity require careful chunk sizing.

### bge-base-en-v1.5 (768-d)

* Good, because it usually scores higher on retrieval benchmarks.
* Bad, because it is about 3× the parameters and needs twice the vector storage. The gain must clear the switch rule.

### granite-embedding-small-english-r2 / snowflake-arctic-embed-s (384-d)

* Good, because they are drop-ins with no column migration and permissive licences (verify).
* Bad, because they are unproven on our data. The bake-off decides.

### mdbr-leaf-ir / gte-modernbert-base (768-d)

* Good, because they are modern, strong retrievers.
* Bad, because they need the additive 768-d migration and have higher CPU cost.

### nomic-embed-text-v1.5

* Good, because it has long context and Matryoshka dimensions.
* Bad, because its model card loads it with remote code (verify). That conflicts with the no-remote-code rule, so it
  is excluded unless it loads without it.

### OpenAI embeddings

* Good, because they are managed and high quality.
* Bad, because every chunk and query would leave the trust boundary (vendor review, LLM02:2026, egress outside the
  allow-list), and there is a network dependency on the hot path.

## More Information

* Spec (private): §8.3, §8.4 (pinning, prompt, switch rule, 768-d path), §9.3 (leakage embedder independence),
  §12.3, §12.4, §12.11. Change record A-14, A-12.
* Research: [embedding-model-choice](../research/embedding-model-choice.md),
  [hybrid-retrieval](../research/hybrid-retrieval.md).
* Related ADRs: ADR-0005, ADR-0007, ADR-0009, ADR-0016 (leakage keeps its own bge-small).
* Revisit when: the bake-off switch rule selects a challenger, or multilingual support lifts NG-07.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (pinned revision, explicit query
  prompt, startup assertion, switch rule, additive 768-d path).
