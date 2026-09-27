---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §6, §8; spec §7.1, §8.5, §8.6, §20 L-16; research hybrid-retrieval
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0007: In-process bm25s keyword retrieval behind `KeywordRetriever`

> **Amended in spec v1.1 (2026-09-27; change record A-14, A-25(e)).**
> * `bm25s` **0.3.11** pinned (MIT), `method="lucene"`, library defaults `k1=1.5`, `b=0.75` (tuned only as a dev
>   ablation).
> * **Code-aware tokenizer.** It emits a whole compound (`saml_err_302`), its parts and `http_<status>` tokens. It
>   drops masked PII placeholders at index and query time. No stemming for code-like tokens (anything with a digit or
>   underscore).
> * **Persisted vocabulary.** The index artifact includes the tokenizer vocabulary and stopwords, and the process
>   refuses to serve if they are missing. Query guards: `k` clamped to the corpus size, score-0 results dropped, and
>   the tokenizer guarded by a lock in a bounded thread.
> * The index lives in **both the API process** (`POST /api/v1/retrieval/search`) **and each worker** (A-25(e)).
>   Each process reports its index version (API: `/api/v1/health/ready`; worker: its container health check). The
>   v1.0 `/readyz` and placement conflicts this ADR flagged are resolved.
> * Alternatives updated: ParadeDB `pg_search` Community is **AGPL-3.0**; `pg_textsearch` (PostgreSQL licence) needs
>   PG17+.

## Context and Problem Statement

The brief asks for "Hybrid BM25 + vector retrieval + reranker" to find "exact policy terms and semantic matches"
(brief §6), with "BM25 initially; OpenSearch/Elasticsearch if expanded" (brief §8). Support tickets are full of exact
tokens that dense embeddings handle badly: `SAML-ERR-302`, `HTTP 429`, invoice ids, `acct_` keys, `v2.3.1`.

The corpus is about 2,000 approved chunks. Retrieval has a 1.5 s stage budget (§7.7), and M-08 targets retrieval P95
≤ 600 ms. Keyword retrieval must obey the approved-only rule (S-09), support the ablations (§8.6), and stay behind the
`KeywordRetriever` port.

The v1.0 design missed three details that the ERPROT research found:
* the default bm25s tokenizer splits code-like tokens;
* without a persisted vocabulary, query ids silently mismatch the index;
* bm25s raises when `k` exceeds the corpus size, for example on the tiny CI fixture.

How should BM25 keyword retrieval be implemented for the MVP?

## Decision Drivers

* True BM25 ranking that honours exact tokens such as error codes.
* A tokenizer we control, one that never indexes PII placeholders.
* No extra service or extension on a single CPU VM.
* Approved-only content (S-09), with bounded staleness after publish or retire (L-16: ≤ 60 s).
* Swappability through the port, and measurability through the ablations (M-05).

## Considered Options

1. In-process `bm25s` behind `KeywordRetriever` (chosen)
2. Postgres full-text search (`tsvector` + `ts_rank_cd`)
3. ParadeDB `pg_search` (AGPL-3.0)
4. `pg_textsearch` (PostgreSQL licence; PG17+)
5. OpenSearch / Elasticsearch

## Decision Outcome

Chosen option: "in-process `bm25s`", because it gives real BM25 with a tokenizer we control. It indexes about 2k
chunks in under a second, and adds no service or extension.

Design (spec §8.5):

* **Index:** built from retrievable chunks at process startup, and rebuilt on the `kb.published` event (debounced
  5 s). Persisted to a local volume under its content hash, together with `chunk_keys.json`, `manifest.json`, and the
  tokenizer vocabulary and stopwords. The filters (`is_retrievable`, effective window, plan) apply in-process through
  bm25s `weight_mask`.
* **Tokenizer:** the code-aware splitter described in the note above. Light stemming (PyStemmer) only for non-code
  tokens.
* **Query guards:** `k = min(k, corpus_size)`; drop score-0 results; tokenizer lock plus bounded thread.
* **Consistency:** each process reports its index version. A staleness alert fires when any version lags the latest
  publish by > 60 s (L-16).
* **Defence in depth (proposed):** keyword hits are joined back to `kb_chunks` with `is_retrievable = true` before
  fusion. A retired chunk still in a stale in-memory index then cannot reach a draft during the ≤ 60 s window.
* Postgres FTS (`kb_chunks.tsv`) stays as a documented fallback adapter.

**Verify at build (research `hybrid-retrieval`):** the bm25s 0.3.11 and PyStemmer versions and licences, and the
splitter output on the error-code fixture.

### Consequences

* Good, because exact identifiers match exactly, where dense retrieval fails. The A1–A4 ablations quantify it.
* Good, because PII placeholders never become index terms. A hypothesis test asserts the splitter never emits one.
* Good, because there is no extra service or licence exposure. The database stays the source of truth, and the index
  is disposable.
* Bad, because every process holds its own copy (API plus workers), which means more memory and eventual consistency
  (≤ 60 s). Mitigations: the staleness alert, the proposed SQL re-check, and the index version recorded on every
  `retrieval_runs` row.
* Bad, because a large corpus would make per-process rebuilds costly. The upgrade path (ParadeDB after an AGPL review,
  or `pg_textsearch` on PG17+) is documented.
* Neutral, because a host-level attacker could tamper with the index file on the volume. It is verified by content
  hash at load, and rebuilt from the database on mismatch (proposed).

### Confirmation

* Unit tests (§14.3): the code-aware splitter output is table-driven (`SAML-ERR-302`, `HTTP 429`, `v2.3.1`,
  `acct_1234`). A hypothesis property shows no placeholder token is ever emitted. Missing vocabulary means the process
  refuses to serve.
* `k` clamp test on the CI fixture index; score-0 results dropped.
* `T-RET-approved-only`: the three adversarial drafts never appear, including just after a retirement (the proposed
  re-check test flips `is_retrievable` without a rebuild).
* Retrieval ablations A1–A4 (M-05, `qrels_test` for reporting, `qrels_dev` for tuning). Eval-smoke gate: Recall@5
  ≥ 0.9 on the fixture (§9.10).
* The API readiness (`/api/v1/health/ready`) and worker health check report the index version.
  `tw_bm25_index_version` has a staleness alert at > 60 s.

## Pros and Cons of the Options

### In-process bm25s

* Good, because it is real BM25, fast, tokenizer-controlled and embedded, and rebuildable from the database.
* Bad, because there is one copy per process with eventual consistency, and the persisted vocabulary must be handled
  correctly.

### Postgres FTS

* Good, because it has zero extra dependencies and is transactional. The `tsvector` column already exists.
* Bad, because `ts_rank_cd` is not BM25, and the default parsers split or normalise code-like tokens.

### ParadeDB `pg_search`

* Good, because it is real BM25 inside Postgres with transactional consistency. It is the recommended upgrade if
  multi-process consistency becomes a real problem.
* Bad, because the Community edition is AGPL-3.0 (legal review of the network clause first). Since 0.25.0 it requires
  pgvector, and index replication needs the Enterprise edition. It also needs a non-standard image and extension
  operations.

### `pg_textsearch`

* Good, because it is BM25-style ranking in Postgres under the PostgreSQL licence.
* Bad, because it requires PostgreSQL 17+, which means a database major upgrade (ADR-0005 pins 16).

### OpenSearch / Elasticsearch

* Good, because it is a full search engine that scales horizontally. It is the brief's "if expanded" option.
* Bad, because it is a heavy JVM service with its own security configuration. That is overkill for 2k chunks.

## More Information

* Spec (private): §7.1 (process placement), §7.7, §8.5, §8.6, §10 (`kb_chunks.tsv`), §11 (`/retrieval/search`,
  `/health/ready`), §15, §20 L-16. Change record A-14, A-25 (e), W-m2.
* Brief (private): §6, §8. BR-019, BR-031.
* Research: [hybrid-retrieval](../research/hybrid-retrieval.md) (bm25s tokenizer, persistence, `k` clamp, ParadeDB
  and pg_textsearch).
* Related ADRs: ADR-0005, ADR-0008, ADR-0009.
* Revisit when: more than one worker replica is routine (consider ParadeDB or `pg_textsearch`), or the corpus exceeds
  about 100k chunks.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (bm25s 0.3.11, code-aware tokenizer,
  persisted vocabulary, `k` clamp, API + worker placement).
