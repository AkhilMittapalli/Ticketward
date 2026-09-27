---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §8, §12; spec §7.1, §8.4, §10, §12.4 LLM09:2026, §18; research hybrid-retrieval
informed: contributors; README/resume owner (see resume-bullet consequence)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0005: PostgreSQL 16 with pgvector as the single datastore (one fewer service)

> **Amended in spec v1.1 (2026-09-27; change record A-14, A-28, A-03).**
> * **pgvector 0.8.6 is pinned** (`pgvector/pgvector:0.8.6-pg16` by digest). 0.8.3/0.8.4 fixed HNSW-vacuum
>   corruption.
> * pgvector filters **after** the index scan and returns at most `hnsw.ef_search` candidates. Every vector query
>   therefore sets `hnsw.ef_search = 100` and `hnsw.iterative_scan = relaxed_order` (via `set_config(..., true)` in the
>   same transaction), re-sorts strictly in a materialized CTE, and **repeats the partial-index predicate**
>   (`is_retrievable`) so the index is used.
> * `is_retrievable` = approved AND current version, maintained by approve/retire events. The time-dependent
>   effective window is checked in the query predicate at retrieval time (W-m19).
> * `infra/postgres/init.sql` creates `pgcrypto`, `vector`, `citext` and `pg_trgm`. Alembic `0001_extensions` is an
>   idempotent guard (A-28). The HNSW index is built `CONCURRENTLY`.
> * The resume/README bullet must also name the **fine-tuning method actually used** (LoRA or QLoRA, A-03), next to
>   pgvector.

## Context and Problem Statement

The brief offers "Qdrant or pgvector" for vector retrieval, and PostgreSQL for data and metadata (brief §8). The KB
is small: 112 approved documents plus 3 adversarial drafts (§8.1), about 2,000 chunks. Retrieval must be
**approved-only** (S-09). A chunk may be served only while its document version is approved and current, and inside
its effective window. Retirement must take effect at once.

LLM09:2026 (vector and embedding weaknesses; LLM08 in the 2025 list) is mitigated by filtering on approval and
`org_id` **at the SQL level** (§12.4). The demo runs on one 8 vCPU / 16 GB VM. Backups are a nightly `pg_dump` with
RPO 24 h / RTO 1 h (§15).

There is also a portfolio-honesty issue. The brief's resume bullet names **Qdrant** (brief §12), and the spec
requires every public claim to be true (§18).

Where should dense vectors live, and what does that mean for consistency, security, operations and public claims?

## Decision Drivers

* Consistency between the KB approval workflow and what can be retrieved (S-09, `T-RET-approved-only`).
* SQL-level filtering by approval, effective window, plan and `org_id` (LLM09:2026).
* Operational simplicity on a single VM: fewer services to secure, back up, monitor and patch.
* Adequate recall and latency at about 2k chunks (M-05 Recall@5 ≥ 0.90; M-08 retrieval P95 ≤ 600 ms).
* Truthful README and resume claims (§18).

## Considered Options

1. PostgreSQL 16 + pgvector 0.8.6 (HNSW, cosine, iterative scan) (chosen)
2. Qdrant (documented alternative, stretch goal G-1)
3. Weaviate
4. Chroma

## Decision Outcome

Chosen option: "PostgreSQL 16 + pgvector", because approval state, chunks, vectors, audit and app data share one
transactional store. Approve, retire and index happen in one transaction with no dual write, and there is one fewer
networked service to harden.

Parameters (spec §8.4, §10):

| Setting | Value |
|---|---|
| Column | `vector(384)` |
| Index | HNSW `m=16, ef_construction=64`, `vector_cosine_ops`, partial `WHERE is_retrievable`, built `CONCURRENTLY` in a non-transactional migration step |
| Per query | `hnsw.ef_search = 100`, `hnsw.iterative_scan = relaxed_order`, partial predicate repeated, effective window checked at query time, strict re-sort in a materialized CTE |
| Filters | plan applicability with a lower-weight fallback (tier-filtered query first, topped up from an unfiltered query with a penalty) |

**Verify at build (research `hybrid-retrieval`):** the pgvector image digest. At P5, measure Recall@30 of HNSW vs
exact search on the qrels, and record the result. PostgreSQL 16's upstream support window is about Nov 2028
(verify). A move to PG 17/18 is a future ADR.

### Consequences

* Good, because approval, retirement and embedding are one transaction. A retired document stops being retrievable
  on the vector path at commit time.
* Good, because the security filters (approval, effective window, `org_id`) are ordinary SQL predicates, reviewed and
  tested like other queries.
* Good, because one backup captures vectors with their metadata, and restore drills cover retrieval.
* Bad, because filtered HNSW needs care. Without iterative scans a selective filter returns fewer than *k* rows. The
  v1.1 query settings and the P5 recall check handle this, and an exact scan stays cheap at about 2k chunks.
* Bad, because pgvector lacks some dedicated-engine features at very large scale. This is acceptable for about 2k
  chunks, and the `VectorRetriever` port keeps a swap possible (§7.1).
* **Bad (portfolio accuracy), and a required action: the brief's resume bullet names Qdrant, but v1 does not use
  Qdrant.** The README and resume use the adapted bullet (spec §18):
  "Built a customer-support resolution copilot using a [LoRA or QLoRA — whichever was used] fine-tuned SLM, hybrid
  RAG (BM25 + pgvector + cross-encoder), FastAPI, PostgreSQL, and Docker; …".
  Qdrant is named **only** if stretch goal G-1 is done, meaning a Qdrant `VectorRetriever` adapter is implemented
  **and** benchmarked in the retrieval ablations.
* Neutral, because extensions are created at first init by `init.sql` (superuser) and guarded by Alembic. The app
  role never creates extensions.

### Confirmation

* `T-RET-approved-only` (BR-002, S-09): the three adversarial `draft` docs never appear in any retrieval run, through
  either path (CI assertion, §8.1).
* Integration job (`backend-integration`, §14.5 step 4) on a real pgvector 0.8.6 Postgres:
  * iterative scan returns *k* rows under a restrictive tier filter;
  * `EXPLAIN` shows the partial HNSW index in use;
  * migrations up/down/up.
* M-05 Recall@5 ≥ 0.90 and Recall@1 ≥ 0.65 on `qrels_test` (`make eval-retrieval`). M-08 retrieval P95 ≤ 600 ms.
* `T-SEC-TENANT-filter` (proposed): a second-`org_id` fixture proves cross-org chunks are never returned.
* (proposed) CI step `readme-claims`: fails if the README or `docs/` present Qdrant as a technology *used* (unless the
  G-1 adapter and its ablation row exist), or if the resume bullet names a fine-tuning method that differs from the
  production model's `training_method`.

## Pros and Cons of the Options

### PostgreSQL 16 + pgvector

* Good, because it is one ACID datastore shared by the approval workflow and retrieval, with plain-SQL filters and one
  set of credentials, backups and monitoring.
* Bad, because filtered ANN needs iterative scans and a repeated predicate, and it scales less far than dedicated
  engines.

### Qdrant

* Good, because it is purpose-built, with payload-indexed filtered HNSW, hybrid sparse+dense search and quantization.
  It is also the brief's first-named option.
* Bad, because it is another networked service to secure, and keeping Postgres approval state and Qdrant payloads in
  sync is a dual write. A missed update could serve a retired chunk.

### Weaviate

* Good, because it is feature-rich, with built-in hybrid search.
* Bad, because it is a heavy extra service. Vectorizer modules can call external APIs (egress and PII risk), and the
  dual-write problem remains.

### Chroma

* Good, because it is easy to start with.
* Bad, because embedded mode is per-process and server mode is another service, with weaker filtering and ops
  features. It is not in the brief.

## More Information

* Spec (private): §7.1, §8.2, §8.4, §8.6, §10 (`kb_chunks`, extensions, image pin), §12.4, §15, §18 (README
  accuracy), §21 R-08 (G-1). Change record A-14, A-28, A-03, W-m19.
* Brief (private): §8, §12. BR-002, BR-031, BR-036, BR-066.
* Research: [hybrid-retrieval](../research/hybrid-retrieval.md) (pgvector 0.8.6, iterative scan, filtered-search
  behaviour).
* Related ADRs: ADR-0006, ADR-0007, ADR-0008, ADR-0009, ADR-0012 (method named in claims).
* Revisit when: the corpus grows past about 1M chunks, per-tenant isolation needs separate collections, or G-1 is
  picked up.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (pgvector 0.8.6, iterative scan,
  repeated predicate, method-accurate resume bullet).
