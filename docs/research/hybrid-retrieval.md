# Hybrid Retrieval (bm25s + pgvector + RRF + Cross-Encoder) - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-26
**Status**: Partially resolved. Libraries, APIs, parameters and licenses are verified. CPU reranker latency and the BM25/vector/RRF/rerank ablation numbers must be measured in P5.
**Category**: Retrieval / Search infrastructure
**Linked ADR(s)**: ADR-0005 (PostgreSQL 16 + pgvector), ADR-0007 (bm25s behind `KeywordRetriever`), ADR-0009 (RRF k=60 + cross-encoder)
**Spec sections**: §7.1 (ports), §7.7 (retrieval budget 1.5 s), §8.3–§8.6, §8.9, §9.10 (CI fixture index), §10 (`kb_chunks`, `retrieval_results`), §20 L-16, §21 R-14, §23
**Method**: ERPROT §0. Primary sources only (official repos, source code, docs, papers, model cards). All sources were accessed 2026-09-26.

---

## EXECUTIVE SUMMARY

The hybrid design in §8 holds up, but several parameters and assumptions need to change before P5. Six spec-impact items are listed below.

1. **bm25s works, but its default tokenizer does not preserve error codes reliably.** The current release is 0.3.11 (MIT, published 2026-08-25). Its default pattern `(?u)\b\w\w+\b` keeps `SAML_ERR_302` as one token only when the customer types the underscores. `SAML-ERR-302`, `HTTP 429` and `v2.3.1` get split apart or partly dropped, and masked PII placeholders such as `<EMAIL_1>` become the token `email_1`. This doc gives a code-aware splitter, tested with the stdlib, that emits the whole compound, its parts and `http_<status>` tokens.
2. **bm25s index persistence also needs the tokenizer vocabulary.** Query token ids depend on the saved tokenizer vocab. With a fresh, empty vocab, `update_vocab="if_empty"` silently creates new ids that do not match the index. Two more gotchas from the source: `retrieve()` raises if `k` is larger than the corpus (this will hit the tiny CI fixture index), and `weight_mask` sets filtered documents' scores to 0 rather than removing them.
3. **pgvector: the current release is 0.8.6 (2026-07-29).** HNSW defaults are `m=16`, `ef_construction=64` and `hnsw.ef_search=40`. The README states that filtering runs *after* the index scan and that results are "limited by the size of the dynamic candidate list (`hnsw.ef_search`), which is 40 by default". The spec's settings (vector top-30, `ef_search=40`, post-filters on plan and effective window) can therefore return fewer than 30 rows. Use `hnsw.iterative_scan = relaxed_order` (available since 0.8.0) with `ef_search ≥ 100`, or exact search, which is cheap at about 2k chunks. Also use 0.8.6, which includes the HNSW-vacuum corruption fix from 0.8.3.
4. **The RRF value k = 60 is confirmed** from the original paper (Cormack, Clarke & Büttcher, SIGIR 2009). The authors say k=60 was "near-optimal, but that the choice was not critical" (Table 1: MAP .2072 at k=0, .2145 at k=60, .2098 at k=500).
5. **The reranker has been renamed.** `cross-encoder/ms-marco-MiniLM-L-6-v2` now redirects to `cross-encoder/ms-marco-MiniLM-L6-v2` (Apache-2.0, 22.7M parameters, head revision `233902d2…`). Its config pins an *Identity* activation, so `predict()` returns raw logits and the sigmoid for τ_ret has to be applied explicitly. The only published speed figure is 1,800 docs/s on a **V100 GPU**. The spec's "~15 ms/pair on CPU" is **UNVERIFIED** and must be measured. ModernBERT rerankers (gte-reranker-modernbert-base, granite-embedding-reranker-english-r2; both Apache-2.0, 149M parameters) are candidates for quality improvements, not the default.
6. **ParadeDB `pg_search` is still the upgrade path, with caveats.** The license is confirmed as AGPL-3.0 (Community edition). The current release is v0.25.10 (2026-09-23). It supports Postgres 15+, has required pgvector since 0.25.0, and uses the index syntax `USING paradedb` (`USING bm25` is kept as an alias). Community edition is single-node: physical replication of ParadeDB indexes (HA, read replicas) requires Enterprise. A permissive alternative, `pg_textsearch` (PostgreSQL license, v1.4.0), supports only Postgres 17 and 18, so it would require leaving PG16.

---

## QUESTIONS

| # | Question (spec §23 + implementer needs) | Answered in |
|---|---|---|
| Q1 | How should the bm25s tokenizer handle error codes (`SAML_ERR_302`, `HTTP 429`, `acct_…`)? What is the current API, and how does persistence work? | F1, D1 |
| Q2 | What are pgvector's HNSW parameters and filtered-search behaviour (iterative index scans, ≥0.8)? Which cosine opclass? Which version and image? | F2, D2 |
| Q3 | Which RRF k? | F3, D3 |
| Q4 | Which reranker, how fast on CPU, and how are its scores normalized? | F4, D4 |
| Q5 | What is the ParadeDB `pg_search` upgrade path and license? What alternatives exist? | F5, D5 |
| Q6 | How does the SQLAlchemy 2.0 async + pgvector-python integration look in code? | F2, D2 snippet |
| Q7 | What gotchas affect CI, multi-worker consistency and evaluation? | F1, F2, Open Risks |

---

## FINDINGS

All links below were accessed 2026-09-26.

### F1. bm25s: versions, API, tokenizer behaviour, persistence

**Version and license.** PyPI `bm25s` 0.3.11, uploaded 2026-08-25. Earlier 0.3.x releases date from 2026-03 to 2026-07 and 0.3.0 from 2026-02-17. The license is MIT, Python ≥3.8, and the only hard dependency is numpy. Optional extras are `core` (orjson, tqdm, PyStemmer, numba), `stem`, `hf`, `mcp` and `cli` ([PyPI JSON](https://pypi.org/pypi/bm25s/json), [GitHub README](https://github.com/xhluca/bm25s)). OSV reports no known vulnerabilities for 0.3.11 ([OSV API](https://api.osv.dev/v1/query)).

**API.** Read from source ([`bm25s/__init__.py`](https://github.com/xhluca/bm25s/blob/main/bm25s/__init__.py), [`bm25s/tokenization.py`](https://github.com/xhluca/bm25s/blob/main/bm25s/tokenization.py)):

| Symbol | Signature (defaults) | Notes |
|---|---|---|
| `bm25s.tokenize` | `(texts, lower=True, token_pattern=r"(?u)\b\w\w+\b", stopwords="english", stemmer=None, return_ids=True, show_progress=True, leave=False, allow_empty=True)` | Module-level helper. The `stemmer` must have `stemWords` or be a *list* callable. |
| `bm25s.tokenization.Tokenizer` | `(lower=True, splitter=r"(?u)\b\w\w+\b", stopwords="english", stemmer=None)` | `splitter` can be a regex string or a callable `str -> list[str]`. A PyStemmer object is converted to its per-word `stemWord` method. |
| `Tokenizer.tokenize` | `(texts, update_vocab="if_empty", leave_progress=False, show_progress=True, length=None, return_as="ids", allow_empty=True)` | `return_as` ∈ {`ids`, `string`, `tuple`, `stream`}. `update_vocab` ∈ {True, False, `"if_empty"`, `"never"`}. |
| `Tokenizer.save_vocab / load_vocab / save_stopwords / load_stopwords` | `(save_dir, vocab_name="vocab.tokenizer.json")` etc. | The query path needs these (see gotcha 1). |
| `bm25s.BM25` | `(k1=1.5, b=0.75, delta=0.5, method="lucene", idf_method=None, dtype="float32", int_dtype="int32", corpus=None, backend="numpy", …)` | Variants: `robertson`, `atire`, `bm25l`, `bm25+`, `lucene` (default, "exact" Lucene BM25). |
| `BM25.index` | `(corpus, create_empty_token=True, show_progress=True, leave_progress=False)` | Accepts a list of token lists (str), a list of id lists, or a `Tokenized`. |
| `BM25.retrieve` | `(query_tokens, corpus=None, k=10, sorted=True, return_as="tuple", show_progress=True, n_threads=0, chunksize=50, backend_selection="auto", weight_mask=None)` | Returns `(documents, scores)` arrays of shape `(n_queries, k)`. |
| `BM25.save` / `BM25.load` | `save(save_dir, corpus=None, …, allow_pickle=False)`; `load(save_dir, …, load_corpus=False, mmap=False, allow_pickle=False, load_vocab=True)` | Arrays are saved with `np.save(..., allow_pickle=False)` by default. There is no pickle deserialization on load. |

**What the default pattern does to codes.** Verified with Python's `re`, which is the module bm25s imports:

| Input (after lower-casing) | Default `(?u)\b\w\w+\b` tokens | Problem |
|---|---|---|
| `SAML_ERR_302` | `saml_err_302` | Only one token. A query written `saml err 302` has zero overlap with it. |
| `SAML-ERR-302` | `saml`, `err`, `302` | The compound is lost. |
| `HTTP 429` | `http`, `429` | Acceptable, but there is no joint token. |
| `app v2.3.1` | `app`, `v2` | `3` and `1` are single characters and get dropped. |
| `<EMAIL_1> said hi` | `email_1`, `said`, `hi` | The masked-PII placeholder becomes a searchable term (noise and false matches). |
| `webhook-v2` | `webhook`, `v2` | The compound is lost. |

**Gotchas from the source:**

1. **Query ids depend on the tokenizer vocabulary.** With `update_vocab="if_empty"` (the default), an *empty* tokenizer (a fresh process that never loaded the vocab) sets `update_vocab=True` and assigns new ids. Those ids do not match the index, which causes silently wrong retrieval. With a loaded vocab and `update_vocab=False`, unknown query words are dropped. If no known words remain, the `""` empty token is used. Always persist `save_vocab` and `save_stopwords` next to the index, and load them before serving.
2. **`retrieve()` raises `ValueError` when `k > num_docs`.** The message is "corpus size should be larger than top-k". The CI eval-smoke "tiny fixture index" (§9.10) will trip on `k=30`, so clamp `k = min(k, n_docs)`.
3. **`weight_mask` is multiplicative.** The code comment reads: "scores for the masked documents will be set to 0 to avoid returning them". Documents with a score of 0 can still fill the top-k when few documents match. Post-filter `score > 0` *and* the mask.
4. **Progress bars are on by default.** `show_progress=True` on `tokenize`, `index`, `retrieve`, `save` and `load` sends tqdm output to worker logs, so pass `show_progress=False`.
5. **The stemmer contracts differ.** `Tokenizer` wants a per-word callable (it extracts PyStemmer's `stemWord`), while module-level `tokenize()` wants a list callable (`stemWords`).
6. **`Tokenizer` is not thread-safe.** It updates its `word_to_stem` cache even when `update_vocab=False`. Serialize query tokenization (a lock, or a `CapacityLimiter(1)` around the thread offload).
7. BM25 scores are unbounded and query-dependent. Never threshold them. Use them only as ranks feeding RRF.

### F2. pgvector: version, HNSW, filtering, iterative scans, Python integration

**Versions** ([CHANGELOG](https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md), [README](https://github.com/pgvector/pgvector)):

| Version | Date | Relevance |
|---|---|---|
| 0.8.0 | 2024-10-30 | Adds iterative index scans and "improved cost estimation for better index selection when filtering". Drops PG12. |
| 0.8.1 | 2025-09-04 | Postgres 18 rc1 compatibility. |
| 0.8.2 | 2026-02-25 | Fixes a buffer overflow in parallel HNSW index builds. |
| 0.8.3 | 2026-06-17 | Fixes "possible index corruption with HNSW vacuuming". |
| 0.8.4 | 2026-06-30 | Fixes "hnsw graph not repaired" errors and insert errors during HNSW vacuum. |
| **0.8.6** | **2026-07-29** | Latest release (IVFFlat and sparsevec fixes). Docker tags include `pgvector/pgvector:0.8.6-pg16` (bookworm) and `0.8.6-pg16-trixie`. |

**HNSW options (README):** `m` is "the max number of connections per layer (16 by default)"; `ef_construction` is "the size of the dynamic candidate list for constructing the graph (64 by default)"; `hnsw.ef_search` is "40 by default". Use `SET LOCAL` inside a transaction to scope it. Supported types are `vector` up to 2,000 dimensions and `halfvec` up to 4,000.

**Filtering is applied after the ANN scan.** The README says: "With approximate indexes, filtering is applied *after* the index is scanned. If a condition matches 10% of rows, with HNSW and the default `hnsw.ef_search` of 40, only 4 rows will match on average." The troubleshooting section adds: "Results are limited by the size of the dynamic candidate list (`hnsw.ef_search`) … There may be even less results due to dead tuples or filtering conditions." The spec asks for vector **top-30** with `ef_search=40` and post-filters (`plans_applicable ∋ tier`, effective window). That combination can return fewer than 30 candidates.

**Iterative index scans (≥0.8.0).** `SET hnsw.iterative_scan = strict_order | relaxed_order` makes the scan "automatically scan more of the index until enough results are found (or it reaches `hnsw.max_scan_tuples`)". The default for `max_scan_tuples` is 20,000 and `hnsw.scan_mem_multiplier` defaults to 1. `relaxed_order` "provides better recall" and can be re-ordered strictly with a `MATERIALIZED` CTE plus `ORDER BY distance + 0` (the `+ 0` is needed on PG17+).

**Other operational facts (README):**
- The index is used only when the query has `ORDER BY <distance operator> ASC LIMIT n`. `ORDER BY 1 - (embedding <=> q) DESC` does not use the index.
- A partial index (`… WHERE is_retrievable`) is used only if the query repeats a predicate that implies it.
- Cosine search uses `vector_cosine_ops` with `<=>`. "If vectors are normalized to length 1 … use inner product for best performance" (`<#>`, `vector_ip_ops`). BGE outputs are normalized (see `embedding-model-choice.md`).
- "if the table is small, a table scan may be faster." With about 2,000 chunks, exact search is fast and has perfect recall.
- Builds run faster when the graph fits in `maintenance_work_mem`. If you raise it, the container's `--shm-size` must be at least that large for parallel HNSW builds. In production, build indexes with `CREATE INDEX CONCURRENTLY`.
- `NULL` vectors and, for cosine, zero vectors are not indexed.

**pgvector-python** is 0.5.0 (2026-07-06) ([README](https://github.com/pgvector/pgvector-python)). SQLAlchemy usage is `from pgvector.sqlalchemy import VECTOR` (also `HALFVEC`, `BIT`, `SPARSEVEC`) with a `mapped_column(VECTOR(384))` column, `Item.embedding.cosine_distance(q)` and `Index(..., postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"})`. Driver-level `register_vector` is only needed for `ARRAY(VECTOR)` columns or raw asyncpg queries.

### F3. RRF

The paper ([Cormack, Clarke, Büttcher, SIGIR '09, PDF](http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)) defines `RRFscore(d) = Σ_{r∈R} 1/(k + r(d))`. It states that "k = 60 was fixed during a pilot investigation and not altered during subsequent validation". It also says the pilot "indicated that k = 60 was near-optimal, but that the choice was not critical" (Table 1: MAP .2072 at k=0, .2139 at 30, .2145 at 60, .2142 at 100, .2098 at 500). The rationale given: the constant k "mitigates the impact of high rankings by outlier systems".

Implementation notes:
- Ranks are **1-based**.
- A document missing from one list contributes nothing from that list.
- Ties need a deterministic tie-break (tested stdlib snippet in D3).
- If tuning is wanted as an ablation, `ranx` 0.3.21 (MIT) offers `fuse(...)` and `optimize_fusion(...)` over qrels ([ranx](https://github.com/AmenRa/ranx)). Fitting k on the test qrels would be leakage, so any tuning uses a dev split.

### F4. Reranker: model facts, score semantics, CPU latency

| Model (HF id) | License | Params | Max len | Published quality (source) | Published speed |
|---|---|---|---|---|---|
| `cross-encoder/ms-marco-MiniLM-L6-v2` (the spec's `…-L-6-v2` redirects here) | Apache-2.0 | 22.7M | 512 (`max_position_embeddings`) | NDCG@10 TREC-DL19 **74.30**, MRR@10 MS MARCO dev **39.01** ([card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)) | 1,800 docs/s "computed on a V100 GPU" |
| `cross-encoder/ms-marco-MiniLM-L12-v2` (reference) | Apache-2.0 | ~33M | 512 | 74.31 / 39.02 (same card); BEIR avg 53.2 in the IBM table | 960 docs/s (V100) |
| `Alibaba-NLP/gte-reranker-modernbert-base` | Apache-2.0 | 149M | 8,192 | BEIR avg 56.73 ([card](https://huggingface.co/Alibaba-NLP/gte-reranker-modernbert-base)); 56.1 in IBM's table | not published; needs transformers ≥4.48 |
| `ibm-granite/granite-embedding-reranker-english-r2` (released 2025-09-08) | Apache-2.0 | 149M | 8,192 | BEIR avg 55.8 ([card](https://huggingface.co/ibm-granite/granite-embedding-reranker-english-r2)) | not published |
| `BAAI/bge-reranker-v2-m3` | Apache-2.0 | 0.6B | 512 (examples) | BEIR/MIRACL charts ([card](https://huggingface.co/BAAI/bge-reranker-v2-m3)) | none; likely too heavy for 20 pairs in the CPU budget (**UNVERIFIED**) |

**Score semantics (important for τ_ret = 0.35).** The MiniLM config contains `"sbert_ce_default_activation_function": "torch.nn.modules.linear.Identity"`, and the card shows raw scores such as `[8.607138 -4.320078]`. In sentence-transformers the default activation is resolved from the config first and falls back to `Sigmoid` only when `num_labels == 1` and no config value exists ([`cross_encoder/model.py`](https://github.com/huggingface/sentence-transformers/blob/main/sentence_transformers/cross_encoder/model.py)). So the sigmoid must be explicit (`activation_fn=torch.nn.Sigmoid()`), and **τ_ret is specific to each reranker**: swapping rerankers requires re-fitting it.

**sentence-transformers 6.x** (6.1.0 released 2026-09-18, Apache-2.0) requires transformers v5, torch ≥2.2 and huggingface-hub v1. `predict()`/`rank()` now upcast scores to float32 before the activation, and `rank()` returns Python floats ([migration guide](https://sbert.net/docs/migration_guide.html), [releases](https://github.com/UKPLab/sentence-transformers/releases)). The `CrossEncoder(..., backend="onnx", model_kwargs={"file_name": "onnx/model_qint8_avx512.onnx"})` path is supported ([efficiency docs](https://sbert.net/docs/cross_encoder/usage/efficiency.html)). The MiniLM-L6 repo ships `onnx/model_qint8_avx512.onnx`, `model_qint8_avx512_vnni.onnx`, `model_quint8_avx2.onnx`, `model_qint8_arm64.onnx` and `model_O1–O4.onnx` ([HF tree API](https://huggingface.co/api/models/cross-encoder/ms-marco-MiniLM-L6-v2/tree/main/onnx)).

**CPU latency.** No primary source publishes CPU latency for these models. The spec's "~15 ms/pair; top-20 ≈ 300 ms" is **UNVERIFIED** and has to be measured on the 8 vCPU / 16 GB reference box (protocol in the checklist).

**Data-license note.** The MiniLM cross-encoders are trained on MS MARCO (the card lists `sentence-transformers/msmarco`). IBM's granite card says it avoided MS MARCO "due to its non-commercial license". This is fine for a synthetic-data portfolio demo, but it belongs in the license review (R-10) before any commercial reuse.

### F5. ParadeDB `pg_search` and alternatives

- **License:** "ParadeDB Community is licensed under the GNU Affero General Public License v3.0" (GitHub API SPDX `AGPL-3.0`). ParadeDB Enterprise is commercial ([README](https://github.com/paradedb/paradedb), [enterprise doc](https://github.com/paradedb/paradedb/blob/main/docs/operate/deploy/enterprise.mdx)). For non-profits and non-commercial open-source projects, the enterprise doc says: "We provide complimentary access on a case-by-case basis."
- **Release:** v0.25.10, published 2026-09-23 (GitHub releases API).
- **Postgres support:** "ParadeDB supports Postgres 15+". The `latest` Docker tag ships PG18, and prebuilt `.deb`/`.rpm` packages exist for Debian 12/13, Ubuntu 24.04/26.04 and RHEL 9/10 ([install](https://github.com/paradedb/paradedb/blob/main/docs/start/install.mdx), [extension install](https://github.com/paradedb/paradedb/blob/main/docs/operate/deploy/self-hosted/extension.mdx)). Installing into an existing Postgres requires superuser. "As of `0.25.0`, `pg_search` relies on `pgvector`'s `vector` type, making it a required extension."
- **Syntax** (docs at tag v0.25.10): `CREATE INDEX search_idx ON t USING paradedb (id, description, …) WITH (key_field='id');`, and "`USING bm25` remains supported as a backwards-compatible alias". The operators are `|||` (match any), `&&&` (match all), `===` (exact term), `###` (phrase) and `@@@` (query builder / parser) ([operators](https://github.com/paradedb/paradedb/blob/main/docs/reference/operators-and-functions.mdx)). For error codes, the `pdb.source_code` tokenizer *splits* snake_case (`my_variable` → `my`, `variable`). Exact code matching needs `pdb.literal` or multiple tokenizers per field.
- **Topology:** "ParadeDB Community can run as a single-node extension install. Use ParadeDB Enterprise when ParadeDB indexes need physical replication for high availability, failover, or read replicas that can serve ParadeDB queries." It is a covering index, so adding columns requires a `REINDEX` ([limitations](https://github.com/paradedb/paradedb/blob/main/docs/concepts/limitations.mdx)).
- **Permissive alternative:** `timescale/pg_textsearch` uses the PostgreSQL license and is at v1.4.0 (2026-08-18). The README states "pg_textsearch supports PostgreSQL 17 and 18." It uses `CREATE INDEX … USING bm25(content) WITH (text_config='english')` and `ORDER BY content <@> 'query'`. Tokenization follows Postgres text-search configurations, so code-token behaviour must be tested ([README](https://github.com/timescale/pg_textsearch)). It is **not usable on PG16**.

---

## DECISION / RECOMMENDATION

**D1 Keyword retrieval: keep ADR-0007 (bm25s 0.3.11), with the tokenizer and persistence changes below.** Use `method="lucene"` with the library defaults `k1=1.5`, `b=0.75`. Tune k1/b only as a dev-split ablation.

```python
# backend/src/ticketward/retrieval/bm25.py  (sketch; the splitter and RRF were tested with stdlib re)
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import bm25s
import numpy as np
import Stemmer  # PyStemmer (bm25s[stem])
from bm25s.tokenization import Tokenizer

# bm25s lower-cases BEFORE calling the splitter, so these patterns are case-insensitive.
_PLACEHOLDER = re.compile(r"<[a-z][a-z_]*_\d+>", re.I)          # masked PII placeholders (§5.6)
_HTTP_STATUS = re.compile(r"(?<![\w-])(?:http|status)(?:\s+code)?[\s:#]*([1-5]\d\d)\b", re.I)
_COMPOUND = re.compile(r"[a-z0-9]+(?:[_\-./:][a-z0-9]+)+")
_WORD = re.compile(r"[a-z0-9]{2,}")
_SEP = re.compile(r"[_\-./:]")
_CODE_LIKE = re.compile(r"[\d_]")
_stemmer = Stemmer.Stemmer("english")


def code_aware_split(text: str) -> list[str]:
    """saml-err-302 -> saml_err_302, saml, err, 302 ; 'HTTP 429' -> http, 429, http_429."""
    text = _PLACEHOLDER.sub(" ", text)
    tokens: list[str] = []
    covered: list[tuple[int, int]] = []
    for m in _COMPOUND.finditer(text):
        raw = m.group(0).strip("./:-_")
        if not any(c.isdigit() for c in raw) and "_" not in raw and "-" not in raw:
            continue                                   # 'e.g', 'and/or' are not codes
        tokens.append(_SEP.sub("_", raw))
        tokens.extend(p for p in _SEP.split(raw) if len(p) >= 2)
        covered.append(m.span())
    tokens.extend(m.group(0) for m in _WORD.finditer(text)
                  if not any(s <= m.start() < e for s, e in covered))
    tokens.extend(f"http_{c}" for c in _HTTP_STATUS.findall(text))
    return tokens


def _stem_unless_code(word: str) -> str:
    return word if _CODE_LIKE.search(word) else _stemmer.stemWord(word)


def make_tokenizer() -> Tokenizer:
    return Tokenizer(lower=True, splitter=code_aware_split, stopwords="english", stemmer=_stem_unless_code)


@dataclass(frozen=True)
class Bm25Index:
    retriever: bm25s.BM25
    tokenizer: Tokenizer
    chunk_keys: list[str]        # position i == bm25s doc id i
    version: str                 # content hash, exposed in /health/ready (§8.5)
    lock: threading.Lock          # Tokenizer mutates its stem cache on every call


def build(chunks: list[tuple[str, str]], root: Path) -> Bm25Index:
    """chunks: (chunk_key, '{title} > {heading_path}\\n{content}') for approved AND retrievable chunks only."""
    chunks = sorted(chunks)
    h = hashlib.sha256()
    for key, text in chunks:
        h.update(key.encode()); h.update(b"\x00"); h.update(text.encode()); h.update(b"\x00")
    version = h.hexdigest()[:16]
    tok = make_tokenizer()
    ids = tok.tokenize([t for _, t in chunks], update_vocab=True, return_as="ids", show_progress=False)
    retriever = bm25s.BM25(method="lucene")
    retriever.index(ids, show_progress=False)
    target = root / version
    retriever.save(target, show_progress=False)            # allow_pickle=False by default
    tok.save_vocab(save_dir=str(target))                   # REQUIRED for correct query ids
    tok.save_stopwords(save_dir=str(target))
    keys = [k for k, _ in chunks]
    (target / "chunk_keys.json").write_text(json.dumps(keys))
    (target / "manifest.json").write_text(json.dumps({"version": version, "n": len(keys), "bm25s": bm25s.__version__}))
    return Bm25Index(retriever, tok, keys, version, threading.Lock())


def load(target: Path) -> Bm25Index:
    retriever = bm25s.BM25.load(target, load_vocab=True, show_progress=False)
    tok = make_tokenizer()
    tok.load_vocab(str(target))
    tok.load_stopwords(str(target))
    keys = json.loads((target / "chunk_keys.json").read_text())
    return Bm25Index(retriever, tok, keys, target.name, threading.Lock())


def search(ix: Bm25Index, query: str, k: int, allowed: np.ndarray | None = None) -> list[tuple[str, float]]:
    """allowed: float32 mask of shape (n_docs,), 1.0 = passes plan/effective filters. Run via anyio.to_thread."""
    with ix.lock:
        q = ix.tokenizer.tokenize([query], update_vocab=False, return_as="ids", show_progress=False)
    k_eff = min(k, len(ix.chunk_keys))                     # retrieve() raises if k > corpus size
    docs, scores = ix.retriever.retrieve(q, k=k_eff, weight_mask=allowed, show_progress=False)
    return [(ix.chunk_keys[int(d)], float(s)) for d, s in zip(docs[0], scores[0]) if s > 0.0]
```

**D2 Vector retrieval: keep ADR-0005 and pin `pgvector/pgvector:0.8.6-pg16` by digest.** Keep the HNSW build defaults (`m=16`, `ef_construction=64`). At query time set `hnsw.ef_search = 100` (≥ about 3× the top-30) and `hnsw.iterative_scan = relaxed_order`, then re-sort strictly. Keep `vector_cosine_ops`. `vector_ip_ops` is an optional speed-up because BGE vectors are unit-normalized. Changing it requires an index rebuild, so decide before P5.

```python
# backend/src/ticketward/retrieval/vector.py  (SQLAlchemy 2.0 Core, no raw SQL strings; see §0/§12.8)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ticketward.db.models import KbChunk, KbDocumentVersion  # KbChunk.embedding = mapped_column(VECTOR(384))


async def vector_search(session: AsyncSession, q: list[float], tier: str, k: int = 30) -> list[tuple[str, float]]:
    distance = KbChunk.embedding.cosine_distance(q).label("distance")      # renders `embedding <=> :param`
    relaxed = (
        select(KbChunk.chunk_key, distance)
        .join(KbDocumentVersion, KbDocumentVersion.id == KbChunk.document_version_id)
        .where(KbChunk.is_retrievable)                     # same expression as the partial-index predicate
        .where(KbDocumentVersion.plans_applicable.any(tier))
        .order_by(distance)                                # ASC distance + LIMIT, or the index is not used
        .limit(k)
        .cte("relaxed")
        .prefix_with("MATERIALIZED")                       # WITH relaxed AS MATERIALIZED (...)
    )
    stmt = select(relaxed.c.chunk_key, relaxed.c.distance).order_by(relaxed.c.distance + 0)  # '+ 0': PG17+
    # Equivalent of SET LOCAL without a raw SQL string: set_config(name, value, is_local => true).
    # Must run in the SAME transaction as the query (AsyncSession autobegin; do not commit in between).
    await session.execute(select(func.set_config("hnsw.ef_search", "100", True)))
    await session.execute(select(func.set_config("hnsw.iterative_scan", "relaxed_order", True)))
    rows = (await session.execute(stmt)).all()
    return [(r.chunk_key, 1.0 - float(r.distance)) for r in rows]
```

Check this snippet in a unit test by compiling the statement to PostgreSQL SQL, and in an integration test by running `EXPLAIN` to confirm that (a) `AS MATERIALIZED` is rendered and (b) the plan uses the partial HNSW index. Spec §8.6 prefers a lower-weight fallback over a hard filter for plan applicability. If that is kept, run the tier-filtered query first and top up from an unfiltered query with a penalty. At P5, measure Recall@30 of this query against exact search (`set_config('enable_indexscan','off', true)`) on `qrels.v1`. If they are identical at v1 scale, keep HNSW for scale-readiness and record the result.

**D3 Fusion: RRF with k=60, unweighted, top-30 ∪ top-30 → top-20.** Store both per-list ranks, as `retrieval_results` already does.

```python
from collections import defaultdict

def rrf(rankings: dict[str, list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Cormack et al. 2009; 1-based ranks; deterministic tie-break (best rank, then id)."""
    score: dict[str, float] = defaultdict(float)
    best: dict[str, int] = {}
    for ranked in rankings.values():
        for rank, doc in enumerate(ranked, start=1):
            score[doc] += 1.0 / (k + rank)
            best[doc] = min(best.get(doc, rank), rank)
    return sorted(score.items(), key=lambda kv: (-kv[1], best[kv[0]], kv[0]))
```

**D4 Reranker: keep ADR-0009's model under its new id, pinned by revision, with an explicit sigmoid.**

```python
import torch
from sentence_transformers import CrossEncoder

RERANKER_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"
RERANKER_REV = "233902d25c440f23af6f7d6e94d2946bac0bee0a"   # HF head sha on 2026-09-26; re-pin at build

reranker = CrossEncoder(RERANKER_ID, revision=RERANKER_REV, max_length=512, device="cpu",
                        activation_fn=torch.nn.Sigmoid())        # config default is Identity (raw logits)
# Optional CPU speed-up (only if P95 misses the budget):
# CrossEncoder(RERANKER_ID, revision=RERANKER_REV, backend="onnx",
#              model_kwargs={"file_name": "onnx/model_qint8_avx512_vnni.onnx"}, activation_fn=torch.nn.Sigmoid())

def rerank(query: str, passages: list[str]) -> list[float]:
    return [float(s) for s in reranker.predict([(query, p) for p in passages], batch_size=32, show_progress_bar=False)]
```

The ModernBERT rerankers (gte-reranker-modernbert-base, granite-embedding-reranker-english-r2) enter ablation A4 as candidates. Promote one only if it improves Recall@5 or MRR@10 on dev *and* the retrieval P95 stays ≤ 600 ms (M-08) on the reference CPU box.

**D5 ParadeDB stays the documented upgrade path, not v1.** It adds AGPL obligations, a non-standard image, pgvector coupling, an extension-DDL/REINDEX workflow and an Enterprise requirement for replica serving. It pays off only if multi-worker BM25 consistency (L-16) becomes a real problem. If a permissive in-Postgres BM25 is wanted later, evaluate `pg_textsearch`, which requires moving to PG17+.

---

## SPEC IMPACT (recorded; the spec was NOT edited)

| # | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §8.4 (`ef_search=40`), §8.6 (vector top-30, filters before scoring) | With post-filtering, HNSW returns at most `ef_search` candidates, and fewer after filters (pgvector README). The "filters applied before scoring" wording does not hold for ANN. | Set `hnsw.ef_search=100` plus `hnsw.iterative_scan=relaxed_order` (materialized CTE re-sort), repeat the partial-index predicate, and add an "exact vs HNSW recall" check to P5. |
| SI-2 | §8.6, §22 ADR-0009 | The reranker HF id was renamed from `ms-marco-MiniLM-L-6-v2` to `ms-marco-MiniLM-L6-v2` (the old id redirects). The model returns raw logits. The CPU figure "~15 ms/pair" is unverified. | Use the new id plus a pinned revision, and state that the sigmoid is applied explicitly. Mark the latency "to be measured" and derive τ_ret per reranker. |
| SI-3 | §8.5 | The bm25s default tokenizer does not preserve hyphenated or spaced codes and indexes PII placeholders. | Name the code-aware splitter and the stemmer bypass explicitly, and require tokenizer vocab persistence in the index artifact. |
| SI-4 | §9.10 (tiny fixture index) | `bm25s.retrieve` raises when k exceeds the corpus size. | Clamp k in `Bm25sKeywordRetriever`. |
| SI-5 | §8.5 (ParadeDB note) | AGPL-3.0 is confirmed. Since 0.25.0 pgvector is required, the syntax is `USING paradedb`, and Community has no replica serving. `pg_textsearch` is a permissive alternative but needs PG17+. | Update the upgrade-path paragraph. |
| SI-6 | §10 image / P0 compose | The latest pgvector is 0.8.6, and 0.8.3/0.8.4 fixed HNSW vacuum corruption. | Pin `pgvector/pgvector:0.8.6-pg16@sha256:…`. |

---

## IMPLEMENTATION CHECKLIST

- [ ] Pin `bm25s==0.3.11`, `PyStemmer`, `numpy` in `backend/uv.lock`. Add the `code_aware_split` tests (the ones in D1 plus hypothesis: the splitter never emits a placeholder token).
- [ ] Put `save_vocab` and `save_stopwords` in the index artifact next to `chunk_keys.json` and `manifest.json`. Refuse to serve if the vocab is missing (health check `bm25_index_version`).
- [ ] Clamp `k`, post-filter `score > 0`, and set `show_progress=False` everywhere. Guard the Tokenizer with a lock. Offload to a thread with a bounded limiter (§14.2).
- [ ] Compose: use `pgvector/pgvector:0.8.6-pg16` pinned by digest. Set `--shm-size` ≥ `maintenance_work_mem` if you build in parallel.
- [ ] Alembic: `CREATE INDEX CONCURRENTLY … USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64) WHERE is_retrievable` (a non-transactional migration step).
- [ ] Vector query: `set_config('hnsw.ef_search','100', true)` and `set_config('hnsw.iterative_scan','relaxed_order', true)` in the same transaction, with a materialized CTE. Add an integration test (testcontainers) asserting that k rows come back under a restrictive tier filter, plus an `EXPLAIN` check that the partial HNSW index is used.
- [ ] RRF: unit and property tests (monotonicity; a doc ranked 1 in both lists always wins).
- [ ] Reranker: pin the id and revision, set `activation_fn=Sigmoid`, `max_length=512`, and batch 20 pairs in one call.
- [ ] **Measure** on the reference box (8 vCPU/16 GB), using 200 queries × 20 pairs with warm-up: P50/P95 for torch fp32 vs ONNX qint8. Record the results in `evals/reports/<date>/retrieval_latency.json`. Budget: retrieval P95 ≤ 600 ms.
- [ ] Ablations A1–A4 on `qrels.v1` (Recall@1/3/5/10, MRR@10, nDCG@10 via `ranx`), with the paired randomization test for RRF vs RRF+rerank. The spec's Recall@k (≥1 relevant in top-k) is ranx's `hit_rate@k`, not ranx's `recall@k`.
- [ ] Re-fit τ_ret (sigmoid space) on the val split so that no-evidence queries abstain (M-07b). Store it in `policy_rule_sets.thresholds`.

## OPEN RISKS / TO VERIFY

| Risk / item | Status |
|---|---|
| CPU latency of MiniLM-L6 (torch vs ONNX int8) on the reference box | **UNVERIFIED**; measure in P5 |
| Whether PyStemmer alters code-like tokens | Avoided by design (the `_stem_unless_code` bypass) |
| Recall of HNSW + `relaxed_order` vs exact search on qrels | Measure in P5 |
| MS MARCO data-license implications for MiniLM (and BGE) in any commercial reuse | License review (R-10) |
| ParadeDB AGPL network-use obligations if adopted later | Legal review before adoption; not v1 |
| bm25s governance/maintainer depth not assessed | Pin the version; the adapter isolates it behind `KeywordRetriever` |
| Multi-worker index staleness (L-16) | Unchanged: version in `/readyz` plus a 60 s lag alert |

## LINKED ADR

- **ADR-0005** PostgreSQL 16 + pgvector. Add the 0.8.6 pin and the iterative-scan settings.
- **ADR-0007** bm25s behind `KeywordRetriever`. Add the tokenizer and persistence decisions from D1. ParadeDB/pg_textsearch remain the alternatives.
- **ADR-0009** RRF k=60 + cross-encoder. Record the renamed model id, the revision pin, the explicit sigmoid and the per-reranker τ_ret.

## SOURCES (all accessed 2026-09-26)

1. bm25s README and source: https://github.com/xhluca/bm25s ; `bm25s/__init__.py`, `bm25s/tokenization.py`, `examples/tokenizer_class.py` (raw.githubusercontent.com, main)
2. bm25s on PyPI (versions, dates, license): https://pypi.org/pypi/bm25s/json
3. pgvector README: https://github.com/pgvector/pgvector ; CHANGELOG: https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md
4. pgvector-python README: https://github.com/pgvector/pgvector-python ; PyPI https://pypi.org/pypi/pgvector/json
5. Cormack, Clarke, Büttcher. "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods", SIGIR 2009: http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
6. ms-marco-MiniLM-L6-v2 model card, config and ONNX tree: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2 ; https://huggingface.co/api/models/cross-encoder/ms-marco-MiniLM-L6-v2
7. sentence-transformers CrossEncoder source: https://github.com/huggingface/sentence-transformers/blob/main/sentence_transformers/cross_encoder/model.py ; v6 migration guide https://sbert.net/docs/migration_guide.html ; releases https://github.com/UKPLab/sentence-transformers/releases ; efficiency https://sbert.net/docs/cross_encoder/usage/efficiency.html
8. gte-reranker-modernbert-base: https://huggingface.co/Alibaba-NLP/gte-reranker-modernbert-base
9. granite-embedding-reranker-english-r2: https://huggingface.co/ibm-granite/granite-embedding-reranker-english-r2
10. bge-reranker-v2-m3: https://huggingface.co/BAAI/bge-reranker-v2-m3
11. ParadeDB repo, docs (install, extension, create index at tag v0.25.10, operators, limitations, enterprise): https://github.com/paradedb/paradedb ; GitHub releases API (v0.25.10)
12. pg_textsearch: https://github.com/timescale/pg_textsearch (README; release v1.4.0)
13. ranx: https://github.com/AmenRa/ranx ; https://pypi.org/pypi/ranx/json
14. OSV vulnerability API: https://api.osv.dev/v1/query

---

**Document Version**: 1.0
**Next Update**: After the P5 latency benchmark and A1–A4 ablations (fill in measured numbers and flip Status to Resolved)
