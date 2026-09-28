# Architecture Decision Records (ADRs)

This folder records every significant architectural decision in Ticketward. Each record uses the
[MADR 4](https://adr.github.io/madr/) format (see [template.md](template.md)). The set matches the ADR list in the
project specification (spec §22, v1.1): ADR-0001..0030, with their v1.1 amendments, and the new ADR-0031..0040. DoD-11
requires the set to be complete.

**Precedence (spec header, v1.1):** owner decisions (D-01..D-06) > project brief > spec > ADRs > Wiki > code comments.
An ADR may change a spec decision only when an owner decision or the brief allows it. The spec is then updated in the
same PR and its version bumped (ADR-0001).

## Index

*Amended* shows the date of the latest in-place amendment. "alignment" means the wording was updated for v1.1 but the
decision is unchanged.

| ADR | Title | Status | Date | Amended | Supersedes |
|---|---|---|---|---|---|
| [0001](ADR-0001-record-architecture-decisions.md) | Record architecture decisions in MADR 4 format | Accepted | 2026-09-27 | 2026-09-27 (alignment) | — |
| [0002](ADR-0002-pin-python-3-12.md) | Pin Python 3.12 for the backend; the ML project allows 3.12–3.13 | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0003](ADR-0003-uv-with-separate-backend-and-ml-locks.md) | Use uv with two independent projects and separate lockfiles | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0004](ADR-0004-fastapi-and-pydantic-v2.md) | FastAPI with Pydantic v2 for the API and data contracts | Accepted | 2026-09-27 | 2026-09-27 (alignment) | — |
| [0005](ADR-0005-postgresql-16-with-pgvector.md) | PostgreSQL 16 with pgvector as the single datastore (one fewer service) | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0006](ADR-0006-sqlalchemy-2-async-asyncpg-alembic.md) | SQLAlchemy 2.0 async with asyncpg and Alembic | Accepted | 2026-09-27 | 2026-09-27 (alignment) | — |
| [0007](ADR-0007-in-process-bm25s-keyword-retrieval.md) | In-process bm25s keyword retrieval behind `KeywordRetriever` | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0008](ADR-0008-bge-small-embeddings-with-hnsw.md) | bge-small-en-v1.5 embeddings (384-d) with an HNSW index | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0009](ADR-0009-rrf-fusion-with-cross-encoder-reranking.md) | RRF fusion (k=60) plus ms-marco-MiniLM-L6-v2 cross-encoder reranking (retrieval only) | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0010](ADR-0010-deterministic-policy-engine-as-data.md) | Deterministic policy engine as versioned data (YAML → DB) | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0011](ADR-0011-base-slm-selected-by-bake-off.md) | Base SLM chosen by bake-off (default candidate: Qwen3.5-2B) | **Proposed** | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0012](ADR-0012-lora-qlora-fine-tuning-with-transformers-peft-trl.md) | LoRA (≤ 2B) or QLoRA (3–4B) SFT with Hugging Face Transformers, PEFT and TRL | Accepted | 2026-09-27 | 2026-09-27 (v1.1; file renamed) | — |
| [0013](ADR-0013-mlflow-tracking-and-registry.md) | MLflow for experiment tracking and model registry | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0014](ADR-0014-ollama-serving-with-json-schema-vllm-production-path.md) | Ollama serving with JSON-schema format; vLLM as the production path | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0015](ADR-0015-llmprovider-abstraction-gated-anthropic-frontier.md) | `LLMProvider` port with a gated Anthropic frontier adapter | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0016](ADR-0016-cross-family-test-set-hard-set-and-bitext-ood.md) | Cross-family test set, human hard set and Bitext OOD set | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0017](ADR-0017-confidence-from-constrained-token-logprobs.md) | Confidence from renormalized path probabilities under constrained decoding, with calibration | **Proposed** | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0018](ADR-0018-modernbert-encoder-baseline.md) | ModernBERT-base as the encoder baseline (E2) | **Proposed** | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0019](ADR-0019-presidio-pii-masking.md) | Presidio PII masking before every model, log and frontier call | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0020](ADR-0020-cookie-jwt-rotating-refresh-csrf-argon2id.md) | Cookie JWT sessions (ES256, rotating refresh, `sid` revocation), signed double-submit CSRF, argon2id | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0021](ADR-0021-rbac-with-five-fixed-roles.md) | RBAC with five fixed roles plus queue-membership object scoping | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0022](ADR-0022-arq-redis-jobs-and-sse.md) | arq on Redis for pipeline jobs; SSE to the UI | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0023](ADR-0023-nextjs-app-router-same-origin-via-caddy.md) | Next.js App Router, TypeScript strict, Tailwind and shadcn/ui; same-origin via Caddy | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0024](ADR-0024-observability-structlog-otel-prometheus.md) | Observability with structlog, OpenTelemetry and Prometheus/Grafana; Langfuse optional | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0025](ADR-0025-rfc-9457-problem-details.md) | RFC 9457 problem details for all API errors | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0026](ADR-0026-docker-compose-caddy-single-vm.md) | Docker Compose and Caddy; single-VM public demo (host decided at P9) | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0027](ADR-0027-target-owasp-asvs-level-2.md) | Target OWASP ASVS 5.0.0 Level 2, with documented exceptions | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0028](ADR-0028-trunk-based-conventional-commits-release-please.md) | Trunk-based development, Conventional Commits, release-please and SemVer | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0029](ADR-0029-taxonomy-v1.md) | Taxonomy v1: 12 intents plus `other_unclear`, 6 queues | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0030](ADR-0030-app-level-aes-gcm-and-crypto-shred-retention.md) | App-level AES-256-GCM for raw ticket text, with retention and purge | Accepted | 2026-09-27 | 2026-09-27 (v1.1) | — |
| [0031](ADR-0031-training-data-generator-families-and-vendor-terms.md) | Training-data generator families and vendor-terms compliance | Accepted | 2026-09-27 | 2026-09-27 (D-07: Family B = DeepSeek-V3.2 on DeepInfra) | — |
| [0032](ADR-0032-evaluation-statistics-protocol-and-pre-registration.md) | Evaluation statistics protocol and pre-registration | Accepted | 2026-09-27 | — | — |
| [0033](ADR-0033-citation-verifier-anchors-nli-and-claim-guards.md) | Citation verifier: lexical anchors + 3-class NLI + claim guards | Accepted | 2026-09-27 | — | — |
| [0034](ADR-0034-prompt-guard-2-secondary-injection-signal.md) | Prompt-injection detector: Llama Prompt Guard 2 22M as a secondary, non-terminal P0 signal | Accepted | 2026-09-27 | — | — |
| [0035](ADR-0035-public-demo-mode-and-demo-locked.md) | Public demo mode (`TW_DEMO_MODE`) with `403 DEMO_LOCKED` privileged actions | Accepted | 2026-09-27 | — | — |
| [0036](ADR-0036-egress-allow-list-via-egress-proxy.md) | Egress allow-list enforced by an egress-proxy container | Accepted | 2026-09-27 | — | — |
| [0037](ADR-0037-crypto-shred-with-per-period-deks-and-deletion-ledger.md) | Crypto-shred with per-period DEKs, a KEK, and a deletion ledger | Accepted | 2026-09-27 | — | — |
| [0038](ADR-0038-research-publishing-via-sync-research.md) | Public research publishing through `scripts/sync_research.py` | Accepted | 2026-09-27 | — | — |
| [0039](ADR-0039-project-and-product-rename-ticketward-taskmoor.md) | Project and product rename: Ticketward / Taskmoor | Accepted | 2026-09-27 | — | — |
| [0040](ADR-0040-mfa-deferred-with-documented-asvs-exception.md) | MFA deferred to after v1.0, with a documented ASVS L2 exception | Accepted | 2026-09-27 | — | — |

**Summary:** 40 ADRs: 37 Accepted and 3 Proposed.
* All 30 of ADR-0001..0030 carry a v1.1 amendment. Three of them (0001, 0004, 0006) are wording alignments only.
* 10 ADRs are new (0031–0040).
* No ADR is superseded: v1.1 refines decisions in place (the ADR-0001 amendment rule).

### Proposed ADRs: evidence needed

| ADR | Why still Proposed | Evidence that moves it to Accepted | Phase |
|---|---|---|---|
| 0011 | The base model is chosen by measurement, not assertion | research `slm-model-selection` refreshed with pinned SHAs and licences; `evals/reports/<date>/bakeoff.md` + `baselines.md` from `make eval-baselines` with the S table (S = 0.40·macro-F1 + 0.25·min critical recall + 0.20·min(1, 5 s / P50) + 0.15·licence) and CIs; CPU P50/P95 per candidate; T4 smoke per finalist; 1-epoch probe of the top 2 logged in MLflow; decision rule applied as written | P2 |
| 0017 | Path-probability confidence depends on the pinned Ollama version's logprobs (available since v0.12.11) and on calibration results | brute-force verification of renormalized path probabilities on a fixture (shared prefix, merged quote token, value outside top-20); calibrator fitted on val; ECE-10 ≤ 0.08 with CIs (M-12) and a reliability diagram; latency within M-08; τ values re-fitted with `justified_by_eval_run_id`; research `confidence-calibration` updated | P3 |
| 0018 | The spec keeps the conditional "ModernBERT-base, or DeBERTa-v3-base if tokenization issues arise" (§9.5), and research `encoder-baseline` is still open | research `encoder-baseline` resolved; tokenization check on 500 train tickets (error codes, `acct_` ids, placeholders, share truncated at 512); T4 fp16 smoke with no NaN/inf; licences verified; E2 results for 3 seeds reproduced | P2 |

## Conventions

* **File names:** `ADR-NNNN-kebab-case-title.md`, with 4-digit numbers that are never reused. A file may be renamed
  only in the PR that updates this index. For example, ADR-0012 was renamed in v1.1 from
  `ADR-0012-qlora-with-transformers-peft-trl.md`, because the method now depends on model size.
* **Statuses:** `Proposed` → `Accepted` → (`Deprecated` | `Superseded by ADR-NNNN`). `Rejected` is kept for
  decisions that were considered and turned down.
* **Amendments (ADR-0001):** a spec version bump that *refines* an Accepted decision amends the ADR in place:
  * a dated "Amended in spec vX.Y" note goes under the title;
  * Context, Decision, Consequences and Confirmation are updated;
  * `date:` and `amended:` are set in the front matter;
  * a line is added to *Status history*.

  A *reversed* decision gets a new ADR that supersedes the old one. The old ADR's status becomes
  `Superseded by ADR-NNNN`, and this index fills the *Supersedes* column.
* **Every ADR has a Confirmation section**, naming the test (`T-*`), metric (`M-*`), CI job or review step that
  enforces it. Items not yet in the spec are labelled "(proposed)".
* **Verify at build:** the spec deliberately does not assert that library, model or vendor versions are current
  (risk R-14). Where an ADR depends on one, it says **verify at build** and names the research topic that holds the
  evidence.
* **Research links:** every research link points to the published copy, `../research/<topic>.md` (owner decision
  D-04; [ADR-0038](ADR-0038-research-publishing-via-sync-research.md)). The published folder is produced by
  `scripts/sync_research.py` from the owner's private working copies.
* **Private documents are cited, never linked:** the specification, the project brief, the spec review and change
  records are private. ADRs cite them as plain text, for example "spec §7.3", "change record A-16" or "owner decision
  D-05". No link may point into the private knowledge base.

## Adding an ADR

1. Run the research protocol first: write the question down, research primary sources with access dates, and record
   the result as a research topic. The topic is published to `docs/research/<topic>.md` by the sync script.
2. Copy [template.md](template.md) to the next free number and fill every section, including Confirmation.
3. Add a row to the index above, and link the ADR from the PR (the "Linked BR-IDs/ADR" field in the PR template).
4. If the ADR changes a spec decision, the spec is updated in the same PR and its version bumped (the spec lives in
   the owner's private knowledge base; say so in the PR).

## Related documents

* [Security threat model](../security/threat-model.md)
* [ASVS 5.0.0 L2 checklist and exceptions register](../security/asvs-l2-checklist.md)
* [Audit events catalogue](../security/audit-events.md)
* [Published research](../research/README.md)
* Spec §22 (ADR list) and §23 (research topics); private, cited as plain text.
