# Embedding Model Choice - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-26
**Status**: Partially resolved. Candidates, licenses, dimensions, prefixes and published scores are verified. The bake-off on `evals/retrieval/qrels.v1.jsonl` is pending because the qrels are built in P5.
**Category**: Retrieval / Embeddings
**Linked ADR(s)**: ADR-0008 (Embeddings bge-small-en-v1.5, 384-d; HNSW)
**Spec sections**: §7.1 (`Embedder` port), §8.4, §8.9, §9.3 (embedding-cosine leakage check), §10 (`kb_chunks.embedding vector(384)`), §12.3 A08 (`trust_remote_code=False`), §14.2, §23
**Method**: ERPROT §0. Model cards, config files in the model repos, library source and official docs. All accessed 2026-09-26.

---

## EXECUTIVE SUMMARY

1. **Keep `BAAI/bge-small-en-v1.5` as the v1 default.** It is MIT-licensed, 33.4M parameters, 384-d, with 512 max tokens. Its card reports MTEB Avg 62.17 and Retrieval 51.68. It is CPU-cheap, fits the existing `vector(384)` schema, and no candidate shows a clear, uncontested win at ≤ 50M parameters.
2. **Implementation gotcha: the query instruction is not applied automatically.** The model's `config_sentence_transformers.json` defines **no `prompts`**. In sentence-transformers 6.x, `encode_query()` uses the `"query"` prompt only "if available in the model's `prompts` dictionary". Calling `encode_query()` on bge-small therefore embeds queries *without* `"Represent this sentence for searching relevant passages: "`. Configure `prompts={"query": …}` at load time. Passages take no instruction. The card says that for v1.5, "no instruction only has a slight degradation", so the ablation measures both settings.
3. **Stronger small options from 2025 exist, but the evidence is mixed.** All published numbers are self-reported, on different suites.
   - **`ibm-granite/granite-embedding-small-english-r2`** is a 384-d drop-in: Apache-2.0, 47M, 8,192 context, released 2025-08-15. IBM's table puts it level with bge-small on MTEB-v2 Retrieval (53.9 vs 53.9) and ahead on long-document, code and multi-turn RAG (LongEmbed 61.9 vs 32.1; MTRAG 48.9 vs 38.2). IBM says it was trained without MS MARCO because of MS MARCO's license.
   - **`MongoDB/mdbr-leaf-ir`** (23M, Apache-2.0) reports BEIR 53.55 vs bge-small 51.65, but its output is **768-d**.
   - **`Snowflake/snowflake-arctic-embed-s`** is a 384-d, Apache-2.0 near-equal of bge-small (MTEB Retrieval 51.98).
   - Larger 768-d options: `gte-modernbert-base` (149M, Apache-2.0, MTEB-en 64.38, BEIR 55.33), `bge-base-en-v1.5` (109M, MIT, 63.55 / 53.25), `nomic-embed-text-v1.5` (Apache-2.0, MRL, prefixes mandatory). `EmbeddingGemma-300m` is under the **Gemma Terms** and gated. `Qwen3-Embedding-0.6B` (Apache-2.0, 1024-d) is too heavy for the CPU default.
4. **No stronger small English embedder released in 2026 turned up** (search on 2026-09-26). The candidates above are 2025 releases. This is a limitation of this search, not proof that none exists. Re-check at P5.
5. **Decision rule:** run the bake-off on a *dev* half of the qrels and adopt a challenger only on a statistically supported gain, measured on the full hybrid pipeline. See D2 and Spec impact SI-3 on selection bias.

---

## QUESTIONS

| # | Question (spec §23 + implementer needs) | Answered in |
|---|---|---|
| Q1 | How does bge-small compare with alternatives *on our qrels*? | D2 (plan; results pending P5) |
| Q2 | What is each model's query/document prefix, and how is it applied in sentence-transformers 6.x? | F3, D1 |
| Q3 | What is the dimension/cost trade-off (storage, index, CPU latency, migration)? | F4, D3 |
| Q4 | What are the licenses? Is `trust_remote_code` needed (spec A08)? | F1, F5 |
| Q5 | Are there stronger small 2025–2026 options? | F1, F2 |
| Q6 | How is this implemented (Embedder adapter, pinning, ONNX, re-embed)? | D1, D3, checklist |

---

## FINDINGS

All links below were accessed 2026-09-26.

### F1. Candidate table (facts as published by each model owner)

| Model | License | Params | Dim (MRL) | Max tokens | Query / document prefix | `trust_remote_code` | Published quality (source, suite) |
|---|---|---|---|---|---|---|---|
| **BAAI/bge-small-en-v1.5** (default) | MIT | 33.4M | 384 | 512 | Q: `Represent this sentence for searching relevant passages: `; D: none | no | MTEB Avg 62.17, Retrieval 51.68 ([card](https://huggingface.co/BAAI/bge-small-en-v1.5)); BEIR 51.65 ([MongoDB table](https://huggingface.co/MongoDB/mdbr-leaf-ir)); MTEB-v2 Retrieval(10) 53.9 ([IBM table](https://huggingface.co/ibm-granite/granite-embedding-small-english-r2)) |
| BAAI/bge-base-en-v1.5 | MIT | 109M | 768 | 512 | same as small | no | MTEB 63.55, Retrieval 53.25 (BGE card) |
| **ibm-granite/granite-embedding-small-english-r2** | Apache-2.0 | 47M | **384** | 8,192 | none documented; no ST prompts file | no (ModernBERT; transformers ≥4.48) | MTEB-v2 Retrieval(10) 53.9; CoIR 53.4; MLDR 40.1; LongEmbed 61.9; MTRAG 48.9; BEIR(15) 50.9; 199 docs/s on H100 vs bge-small's 138 (IBM card) |
| Snowflake/snowflake-arctic-embed-s | Apache-2.0 | 33M | 384 | 512 | Q prompt defined in ST config (same BGE instruction) | no | MTEB Retrieval NDCG@10 51.98 ([card](https://huggingface.co/Snowflake/snowflake-arctic-embed-s)) |
| **MongoDB/mdbr-leaf-ir** | Apache-2.0 | 23M | **768** (Dense 384→768; MRL shown to 256) | 512 (BERT-small base; **UNVERIFIED**) | Q prompt defined (same BGE instruction); D: `""` | no | BEIR 53.55 (sym), 54.03 (asym with teacher `arctic-embed-m-v1.5`) ([card](https://huggingface.co/MongoDB/mdbr-leaf-ir); [arXiv 2509.12539](https://arxiv.org/abs/2509.12539)) |
| Alibaba-NLP/gte-modernbert-base | Apache-2.0 | 149M | 768 | 8,192 | "not required" | no (transformers ≥4.48) | MTEB-en(56) 64.38; BEIR 55.33 ([card](https://huggingface.co/Alibaba-NLP/gte-modernbert-base)) |
| nomic-ai/nomic-embed-text-v1.5 | Apache-2.0 | ~0.1B | 768 (512/256/128/64) | 8,192 | **mandatory** `search_query: ` / `search_document: ` | card: "From transformers v5.5.0 and sentence transformers v5.3.0, `trust_remote_code=True` will no longer be necessary" for text models (**verify** under the pinned versions) | MTEB 62.28 @768, 61.04 @256 ([card](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)) |
| nomic-ai/modernbert-embed-base | Apache-2.0 | 149M | 768 | 8,192 | `search_query: ` / `search_document: ` | no | MTEB 62.62; Retrieval 52.89 (gte card, from the MTEB leaderboard) |
| google/embeddinggemma-300m | **Gemma Terms of Use**; HF-gated (manual) | ~300M | 768 (512/256/128) | 2K | Q: `task: search result \| query: {content}`; D: `title: {title \| "none"} \| text: {content}` | no | MTEB English v2 mean(task) 69.67 ([Google model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card)) |
| Qwen/Qwen3-Embedding-0.6B | Apache-2.0 | 0.6B | 1024 (32–1024) | 32K | Q: `Instruct: {task}\nQuery:{q}`; D: none; the card cites a 1–5% gain from instructions | no (transformers ≥4.51) | MMTEB table in card ([card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)) |
| intfloat/e5-small-v2 (reference) | MIT | 33M | 384 | 512 | `query: ` / `passage: ` (both sides) | no | BEIR 49.04 (MongoDB table) |

### F2. How comparable are these numbers? Not very.

- Each score comes from the model owner's own card, on different suites: MTEB v1 (56 tasks), MTEB v2 subsets, BEIR-15, and vendor-selected long-context or code sets.
- The same model gets different numbers in different tables. bge-small is 51.68 in MTEB-v1 Retrieval on its own card, 51.65 in BEIR in MongoDB's table and 53.9 in MTEB-v2 Retrieval(10) in IBM's.
- granite-small-r2 is *below* bge-small on BEIR-15 in MongoDB's table (50.87 vs 51.65) and level with it on IBM's MTEB-v2 retrieval subset. Its advantages are long-document and multi-turn tasks. Our chunks are capped at 512 tokens and queries use the first 512 tokens of masked ticket text (§8.3, §7.2), so the long-context advantage mostly does not apply.
- Conclusion: **only our own qrels can decide.** Treat the table as a shortlist, not a ranking.

### F3. Prefix mechanics in sentence-transformers 6.x

The source of `SentenceTransformer.encode_query` ([model.py](https://github.com/huggingface/sentence-transformers/blob/main/sentence_transformers/sentence_transformer/model.py)) says: "If no `prompt_name` or `prompt` is provided, it uses a predefined 'query' prompt, if available in the model's `prompts` dictionary". `encode_document` works the same way with `"document"`. The prompt configuration shipped in each repo:

| Model | `config_sentence_transformers.json` prompts | Consequence |
|---|---|---|
| bge-small-en-v1.5 | none (file only has `__version__`) | `encode_query()` adds **nothing**. Pass `prompts={"query": BGE_Q}` to the constructor or `prompt=` per call. |
| snowflake-arctic-embed-s | `{"query": "Represent this sentence for searching relevant passages: "}` | `encode_query()` applies it automatically. |
| mdbr-leaf-ir | `{"query": "Represent …: ", "document": ""}` | automatic |
| granite-embedding-small-english-r2 | no ST config file in the repo | no prefix (the card uses plain `encode`) |
| nomic-embed-text-v1.5 | card shows the prefix inside the text | put the prefixes in `prompts={"query": "search_query: ", "document": "search_document: "}` |

The BGE card says: "In all cases, the documents/passages do not need to add the instruction". It also says that for v1.5, "No instruction only has a slight degradation in retrieval performance compared with using instruction."

### F4. Dimension and cost trade-off

- **Storage:** 384-d float32 is 1,536 bytes per vector and 768-d is 3,072 bytes. With about 2,000 chunks that is about 3 MB vs about 6 MB, which is negligible. `halfvec` halves both if we ever scale (pgvector README).
- **HNSW:** both dimensions sit far below pgvector's 2,000-dimension index limit, and build time at 2k vectors is trivial.
- **CPU latency** is the real cost. Query-time encoding runs once per ticket, on up to 512 tokens, inside the 1.5 s retrieval budget (§7.7) and M-08's retrieval P95 ≤ 600 ms. Encoder compute scales roughly with parameter count per token: 33M → 109–149M is about 3–4.5× (**ANALYTICAL**, not measured). IBM's docs/s figures were measured on H100 GPUs and say nothing about our CPU box. Measure P50/P95 on the reference box.
- **Migration cost:** moving from 384-d to 768-d changes `kb_chunks.embedding vector(384)`, requires a new HNSW index and a full re-embed (`scripts/reindex.py`, ADR-0008), and needs an Alembic migration. 384-d candidates (granite-small-r2, arctic-embed-s) are config-only swaps plus a re-embed.
- **ONNX:** the bge-small repo ships `onnx/model.onnx`. sentence-transformers supports `backend="onnx"` / `"openvino"` for faster CPU inference, as an optional optimization.

### F5. Licensing and supply-chain policy fit

- MIT: BGE, e5. Apache-2.0: granite, arctic, leaf, gte, nomic, Qwen3. EmbeddingGemma is under the Gemma Terms of Use and gated. It is usable, but it adds terms and distribution conditions to review. Not recommended for this portfolio project without a license review (R-10).
- Spec A08 requires `trust_remote_code=False`. sentence-transformers 6.0 says: "Loading models with custom module classes now always requires `trust_remote_code=True`, including local directories and installed packages". Any candidate that needs custom code is excluded unless the policy changes. nomic's card says the requirement was dropped for text models from transformers 5.5 / ST 5.3. Verify under the pinned versions (transformers 5.17.0, sentence-transformers 6.1.0 on PyPI 2026-09) before including it.
- Training-data licenses: IBM notes it did "*not use* the popular MS-MARCO retrieval dataset … due to its non-commercial license". Many other models do use MS MARCO. This does not matter for a synthetic-data demo, but it belongs in the R-10 license review for commercial reuse.

### F6. Coupling with the leakage check (§9.3)

§9.3 flags cross-split pairs at bge-small cosine ≥ 0.92. The BGE card warns: "the similarity distribution of the current BGE model is about in the interval [0.6, 1]. So a similarity score greater than 0.5 does not indicate that the two sentences are similar." Cosine thresholds are model-specific, so the leakage check should keep a **pinned bge-small** even if the retrieval embedder changes.

---

## DECISION / RECOMMENDATION

**D1 Keep ADR-0008: `BAAI/bge-small-en-v1.5`, pinned by revision, with explicit prompts, normalized embeddings and `vector(384)`.**

```python
# backend/src/ticketward/retrieval/embed.py
from __future__ import annotations

from typing import Literal

import anyio
import numpy as np
from sentence_transformers import SentenceTransformer

BGE_QUERY = "Represent this sentence for searching relevant passages: "
# Only pass prompts the repo does NOT already ship (see F3). None => use the repo's own prompts.
PROMPTS: dict[str, dict[str, str] | None] = {
    "BAAI/bge-small-en-v1.5": {"query": BGE_QUERY},
    "BAAI/bge-base-en-v1.5": {"query": BGE_QUERY},
    "Snowflake/snowflake-arctic-embed-s": None,
    "MongoDB/mdbr-leaf-ir": None,
    "ibm-granite/granite-embedding-small-english-r2": None,
    "Alibaba-NLP/gte-modernbert-base": None,
    "nomic-ai/nomic-embed-text-v1.5": {"query": "search_query: ", "document": "search_document: "},
}


class SentenceTransformerEmbedder:
    """Implements domain.ports.Embedder. CPU-bound work runs in a bounded thread (§14.2)."""

    def __init__(self, model_id: str, revision: str, *, max_threads: int = 1) -> None:
        self.model_id = model_id
        self._model = SentenceTransformer(
            model_id, revision=revision, device="cpu", trust_remote_code=False, prompts=PROMPTS[model_id]
        )
        self._model.max_seq_length = min(self._model.max_seq_length or 512, 512)   # chunks are <= 512 tokens
        dim = self._model.get_embedding_dimension()          # v6 name; get_sentence_embedding_dimension() is an alias
        if dim is None:
            raise RuntimeError(f"cannot determine embedding dimension for {model_id}")
        self.dim: int = dim
        self._limiter = anyio.CapacityLimiter(max_threads)

    async def embed(self, texts: list[str], kind: Literal["query", "passage"]) -> list[list[float]]:
        encode = self._model.encode_query if kind == "query" else self._model.encode_document

        def _run() -> np.ndarray:
            return encode(texts, batch_size=32, normalize_embeddings=True,
                          convert_to_numpy=True, show_progress_bar=False)

        vectors = await anyio.to_thread.run_sync(_run, limiter=self._limiter)
        return vectors.astype(np.float32).tolist()
```

At startup, assert that `embedder.dim == settings.embedding_dim == 384` and that `kb_chunks.embedding_model` matches `model_id@revision`. Refuse to serve if either check fails, because mixing vector spaces is silent corruption.

**D2 Bake-off in P5, on our qrels, using the complete pipeline.**

| Item | Protocol |
|---|---|
| Split | Split `qrels.v1` (300 answerable + 40 no-evidence) into **dev** (150 + 20) and **test** (150 + 20), stratified by doc_type and intent. Choose on dev and report M-05 on test (see SI-3). |
| Candidates | Baseline bge-small (with and without the query instruction). 384-d challengers: granite-small-r2, arctic-embed-s. 768-d challengers: mdbr-leaf-ir, bge-base, gte-modernbert-base. nomic is included only if it loads with `trust_remote_code=False`. |
| Runs | A2 (vector-only) and A4 (BM25 ∪ vector → RRF → rerank). **A4 is the decision metric**, because the embedder's value in production is its contribution after fusion and reranking. |
| Metrics | Recall@1/3/5/10, MRR@10 and nDCG@10 at doc level: aggregate chunk→doc by max score, computed with `ranx` 0.3.21 (MIT). **Note:** the spec's Recall@k ("fraction of queries with ≥ 1 relevant doc in top-k", §8.9) is ranx's `hit_rate@k`, *not* ranx's `recall@k`, which is the fraction of relevant docs retrieved. Report both, and label them. Report an error-code query subset separately. For the 40 no-evidence queries, report the top rerank score distribution (abstention, M-07b). |
| Statistics | Paired randomization test (`ranx.compare`) with p < 0.05, plus a 1,000-resample paired bootstrap 95% CI on the ΔRecall@5 (§9.8 convention). |
| Latency | Query-embedding P50/P95 on the 8 vCPU/16 GB box (512-token inputs, warm, 200 samples) and index-build time for the full KB. |
| Switch rule | Adopt a challenger only if dev A4 Recall@5 improves by **≥ +2.0 points** (CI excludes 0), no other metric regresses by more than 1 point, query-embed **P95 ≤ 50 ms**, it is Apache/MIT with no remote code, and a 768-d model also justifies the migration (D3). Otherwise keep bge-small. |

```python
# ml/src/tw_ml/eval/retrieval.py (sketch) - doc-level runs from chunk-level scores
from ranx import Qrels, Run, compare

def to_doc_run(chunk_scores: dict[str, list[tuple[str, float]]]) -> Run:
    run: dict[str, dict[str, float]] = {}
    for qid, scored in chunk_scores.items():
        docs: dict[str, float] = {}
        for chunk_key, s in scored:
            doc_key = chunk_key.split("#c", 1)[0]          # chunk id = {doc_key}#c{n} (§8.3)
            docs[doc_key] = max(docs.get(doc_key, float("-inf")), s)
        run[qid] = docs
    return Run(run)

# Spec Recall@k (§8.9) == ranx "hit_rate@k"; ranx "recall@k" is classic recall - report both, labelled.
# report = compare(qrels=Qrels(qrels_dev), runs=[run_bge, run_granite, run_leaf],
#                  metrics=["hit_rate@1", "hit_rate@5", "recall@5", "mrr@10", "ndcg@10"], max_p=0.05)
```

**D3 If a 768-d model wins, migrate additively.** Add `embedding_v2 vector(768)` and its own partial HNSW index, backfill with `scripts/reindex.py --target embedding_v2`, switch reads behind a setting, and drop `embedding` one release later. Record the change in ADR-0008 (new revision) with the `eval_run_id` that justified it.

---

## SPEC IMPACT (recorded; the spec was NOT edited)

| # | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §8.4 "query instruction prefix per the model card" | sentence-transformers does not apply bge-small's instruction automatically, because the repo defines no prompts (F3). | State that the `Embedder` configures `prompts={"query": …}` explicitly, and add a unit test asserting the query and passage embeddings differ for the same text. |
| SI-2 | §8.4 alternatives list | Add `ibm-granite/granite-embedding-small-english-r2` and `Snowflake/snowflake-arctic-embed-s` (384-d drop-ins) and `MongoDB/mdbr-leaf-ir` (768-d). Note that EmbeddingGemma is under the Gemma Terms (gated) and that nomic's `trust_remote_code` status must be verified against A08. | Update the alternatives sentence. |
| SI-3 | §8.9 / M-05 | Choosing the embedder, the reranker and τ on the same 300 queries used to report M-05 is selection bias, and it inflates Recall@5. | Split the qrels into dev and test (for example 150/150 stratified). Select on dev and report on test. |
| SI-4 | §9.3 leakage check | The cosine threshold 0.92 is specific to bge-small (its similarities concentrate in [0.6, 1]). | Pin bge-small at a fixed revision for the leakage check, independent of the retrieval embedder. |

---

## IMPLEMENTATION CHECKLIST

- [ ] Pin `sentence-transformers==6.1.0` and `transformers==5.17.0` (latest on PyPI 2026-09) in `backend/uv.lock`. Pin the bge-small `revision` SHA in settings (`TW_EMBEDDING_REVISION`).
- [ ] `SentenceTransformerEmbedder` per D1, with the `PROMPTS` registry and `trust_remote_code=False` hard-coded. Add a test that query/passage vectors differ, a dimension assertion and a normalization assertion (‖v‖≈1).
- [ ] Store `embedding_model = "<id>@<revision>"` and `embedding_dim` per chunk (already in §8.4). Health check: an embedder mismatch fails `/health/ready`.
- [ ] P5: split the qrels into dev and test; run the D2 bake-off; commit `evals/reports/<date>/embedder_bakeoff.md` plus JSON.
- [ ] Measure query-embed latency (torch vs `backend="onnx"`) on the reference box and record P50/P95.
- [ ] Keep a pinned bge-small for `ml/datagen/leakage.py`, separate from the runtime embedder.

## OPEN RISKS / TO VERIFY

| Item | Status |
|---|---|
| Actual ranking of candidates on our qrels | Pending P5 bake-off |
| CPU latency of 149M ModernBERT encoders on the reference box | **UNVERIFIED**; measure |
| mdbr-leaf-ir max sequence length and whether truncating to 384 dims (MRL) keeps quality | **UNVERIFIED**; the card shows truncation to 256 |
| nomic v1.5 loading without remote code under transformers 5.17 / ST 6.1 | **UNVERIFIED**; check at build |
| MS MARCO training-data terms for commercial reuse | License review (R-10) |
| Newer 2026 small embedders not found by this search | Re-scan the MTEB leaderboard at P5 |

## LINKED ADR

- **ADR-0008**: keep bge-small-en-v1.5. Add the explicit-prompt rule, the revision pin, the D2 switch rule and the D3 migration path. Alternatives considered are updated per SI-2.

## SOURCES (all accessed 2026-09-26)

1. BAAI/bge-small-en-v1.5 card, `config_sentence_transformers.json`, `modules.json`, ONNX tree: https://huggingface.co/BAAI/bge-small-en-v1.5
2. BAAI/bge-base-en-v1.5 card: https://huggingface.co/BAAI/bge-base-en-v1.5
3. ibm-granite/granite-embedding-small-english-r2 card (raw README): https://huggingface.co/ibm-granite/granite-embedding-small-english-r2
4. Snowflake/snowflake-arctic-embed-s card and ST config: https://huggingface.co/Snowflake/snowflake-arctic-embed-s
5. MongoDB/mdbr-leaf-ir card, `modules.json`, `2_Dense/config.json`, ST config: https://huggingface.co/MongoDB/mdbr-leaf-ir ; paper https://arxiv.org/abs/2509.12539
6. Alibaba-NLP/gte-modernbert-base card: https://huggingface.co/Alibaba-NLP/gte-modernbert-base
7. nomic-ai/nomic-embed-text-v1.5 card: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5 ; nomic-ai/modernbert-embed-base card
8. EmbeddingGemma model card (Google): https://ai.google.dev/gemma/docs/embeddinggemma/model_card ; HF API (license `gemma`, gated): https://huggingface.co/api/models/google/embeddinggemma-300m
9. Qwen/Qwen3-Embedding-0.6B card: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
10. intfloat/e5-small-v2 card: https://huggingface.co/intfloat/e5-small-v2
11. sentence-transformers `SentenceTransformer` source (`encode_query`, constructor): https://github.com/huggingface/sentence-transformers/blob/main/sentence_transformers/sentence_transformer/model.py ; v6 migration guide https://sbert.net/docs/migration_guide.html ; PyPI https://pypi.org/pypi/sentence-transformers/json
12. ranx: https://github.com/AmenRa/ranx
13. pgvector README (dimension limits, halfvec): https://github.com/pgvector/pgvector

---

**Document Version**: 1.0
**Next Update**: After the P5 bake-off (fill in the D2 results table and flip Status to Resolved)
