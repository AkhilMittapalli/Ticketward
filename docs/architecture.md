# Ticketward: Architecture

| Field | Value |
|---|---|
| Document | `docs/architecture.md` |
| Version | 0.1 (P0; master specification v1.1) |
| Date | 2026-09-27 |
| Owner | Akhil Mittapalli |
| Status | **Target architecture.** Most components are planned; [section 8](#8-what-exists-now-and-what-is-planned) lists what exists in P0 and the phase in which the rest lands. Where this page and the spec differ, the spec wins. |
| Source | spec §7 (system architecture), §10 (data), §11 (API), §12.5 (PII masking), §12.11 (networks), §24 (public demo) |
| Related | [ADR index](adr/README.md) · [Threat model](security/threat-model.md) · [Audit events](security/audit-events.md) · [Research notes](research/README.md) · [OpenAPI](openapi.json) |

## 1. Purpose

Ticketward is a human-in-the-loop resolution copilot for B2B SaaS support teams. Its tickets come from **Taskmoor**, a fictional project-management SaaS (Taskmoor is fictional and not affiliated with any real company; all data is synthetic). For every ticket it produces a reviewed, evidence-backed plan: intent, product area, entities and priority; assistive sentiment and churn signals; approved knowledge-base sources; a cited draft reply; a recommended queue and next action; and an escalation-ready handoff brief.

Three rules shape the architecture:

- **A human always decides.** Nothing is sent automatically: "Approve & Mark Sent" copies the text to the clipboard. Refunds, cancellations, payment disputes, security reports, legal or privacy requests and active incidents always go to a person.
- **Code, not the model, chooses the path.** A deterministic policy engine reads labels, calibrated scores, lexicon hits and retrieval scores. It never reads model free text. It picks one of four paths: local draft, frontier draft, clarifying questions or human escalation (spec §7.3).
- **The smallest reliable model comes first.** A fine-tuned small language model runs on CPU through Ollama. A frontier model is an optional, gated fallback for complex cases. It is off by default and only ever sees masked text.

## 2. Components

```text
Browser --HTTPS--> Caddy 2.11  (network edge; the only published ports, 80/443)
                     | /api/*                             | any other path: GET/HEAD only (else 405)
                     v                                    v
   +--------------------------------+       +--------------------------------+
   | API: FastAPI (ticketward.api)  |<------| Web: Next.js (App Router)      |
   |  /api/v1 routers -> services   |  DAL  |  Server Components read via a  |
   |   -> domain / policy -> repos  |       |  server-only DAL; proxy.ts     |
   |  retrieval in-process: bm25s,  |       |  only sets the nonce CSP       |
   |   embedder, reranker           |       +--------------------------------+
   |  internal listener: service    |<---- email-feed worker (ES256 service JWT;
   |   tokens (not routed by Caddy) |      simulated feed, no real e-mail)
   +------+-----------------+-------+
          | enqueue (arq)   | SQL
          v                 v
   +-------------+   +----------------------------------+
   | Redis 7     |   | PostgreSQL 16 + pgvector 0.8.6   |
   | jobs, rate  |   | app data, KB chunks + vectors,   |
   | limits, sid |   | audit log, deletion ledger,      |
   | revocation  |   | encrypted raw text, wrapped DEKs |
   +------+------+   +----------------------------------+
          | jobs (msgpack)          ^ SQL
          v                         |
   +--------------------------------+---+      +--------------------------+
   | Worker: arq pipeline               |----->| Ollama (CPU)             |
   |  sanitize + Presidio PII masking   |      |  tw-triage GGUF (merged) |
   |  triage || hybrid retrieval        |      |  vLLM = documented       |
   |  policy engine -> draft            |      |  production path         |
   |  NLI citation verifier, Prompt     |      +--------------------------+
   |  Guard 2 detector, claim guards    |
   +-----------------+------------------+
                     | HTTPS_PROXY (CONNECT; TLS stays end to end)
                     v
   +------------------------------------+
   | egress-proxy (allow-list; the only |---> Anthropic API (frontier; optional, off by default)
   | container with an internet route)  |---> Hugging Face Hub (build and model-fetch jobs only)
   +------------------------------------+---> HIBP range API (optional breached-password check)

Observability (internal only): structlog JSON -> stdout | OTel SDK -> Collector (redaction allow-list)
  -> Tempo | prometheus_client on api:9464 and worker:9465 -> Prometheus -> Grafana (SSH tunnel)
Offline ML: ml/ (data generation, T4 training, evaluation) -> MLflow registry -> Hugging Face Hub
  (adapter, merged model, GGUF, model card) -> Ollama Modelfile
```

**Process placement (spec §7.1).** The retrieval components (bm25s index, embedder, reranker) run in **both** the API process (for `POST /api/v1/retrieval/search`) and the worker (the pipeline). The worker also hosts the Presidio masker, the NLI verifier and the injection detector. Each process loads its own components and reports them in its own readiness check. Heavy CPU work runs in the worker or in bounded threads, never on the event loop. Only the egress-proxy has an internet route: the worker uses it for the frontier, and the API uses it for the optional breached-password range check.

**Layering rule (enforced by `import-linter`).** Imports flow one way: `api → services → (domain, policy, retrieval, ml, providers) → repositories → db`. `domain` imports nothing from infrastructure, and providers sit behind protocols in `domain/ports.py`. A second contract keeps the policy engine independent of model text: `policy` must not import `providers` or retrieval chunk text.

## 3. Ports and adapters

| Port (`domain/ports.py`) | Adapters |
|---|---|
| `LLMProvider` (`generate_structured`, `generate_text`, `estimate_cost`) | `OllamaProvider` (raw prompts, decoding schema, logprobs), `AnthropicProvider` (frontier; no sampling parameters), `VLLMProvider` (stub + docs), `RulesBaselineProvider` |
| `KeywordRetriever` · `VectorRetriever` | `Bm25sKeywordRetriever` (code-aware tokenizer) · `PgVectorRetriever` (HNSW, iterative scan) |
| `Embedder` · `Reranker` | `SentenceTransformerEmbedder` (`bge-small-en-v1.5`, explicit query prompt) · `CrossEncoderReranker` (`ms-marco-MiniLM-L6-v2`, explicit sigmoid) |
| `SupportVerifier` | `NliSupportVerifier` (number/code anchors, then 3-class NLI with `nli-deberta-v3-base`) |
| `InjectionDetector` | `PromptGuard2Detector` (Llama Prompt Guard 2 22M, 512-token windows; CI uses recorded outputs) |
| `PIIMasker` | `PresidioMasker` (explicit entity list; the reversible map stays server-side) |

Tests inject deterministic stand-ins through FastAPI `Depends`, so CI needs no model server. Only `core/http.py` and the provider adapters may build outbound HTTP clients, and every client goes through the egress proxy.

## 4. Request lifecycle

All paths share steps 0–3 (spec §7.2):

0. **Ingest.** `POST /api/v1/tickets` checks the 256 KB byte cap, validates the body and the `Idempotency-Key` (scoped by principal), reduces card numbers to their last 4 digits, and stores **only the raw text, encrypted**. It then enqueues `process_ticket` and returns `202 {ticket_id, job_id}`.
1. **Sanitize and mask (worker).** The worker applies NFKC, strips invisible Unicode and neutralizes spoofed delimiters and special-token literals. Presidio masking follows, then the masked copy and the encrypted placeholder map are written and a residual-PII scan runs. If masking fails or takes longer than 1 s, the pipeline stops before any model call (P7, fail closed).
2. **Triage and retrieval, in parallel.** The SLM triages the masked text (raw prompt, decoding schema, logprobs → path-probability confidence and P(critical), repair ladder). Hybrid retrieval runs bm25s and pgvector, fuses them with RRF (k = 60) and reranks with a cross-encoder. It only sees chunks that are approved, current and effective. An incident matcher looks for active known incidents.
3. **Policy.** The engine evaluates **every** rule, records every fired rule and takes the path from the highest-precedence terminal rule (section 5).

| Path | Example | What happens |
|---|---|---|
| **Routine** | How-to question with strong evidence | No terminal rule P1–P10 fires, so P11 gives `local_draft`. The SLM drafts from numbered sources, and the citation verifier checks every factual sentence against its cited chunk (anchors → NLI → claim guards). Unsupported sentences are removed; if more than 30% go, the draft falls back to clarifying questions. Results arrive over SSE (heartbeat 20 s). |
| **Complex** | SSO loop + plan entitlement + migration | The complexity score is ≥ 2 and every frontier condition holds, so P10 gives `frontier_draft`. The frontier sees masked text and chunk text only, and the same verifier and guards run. If any condition fails, the ticket falls back to the local draft. |
| **High-risk** | Duplicate charge + "I'll dispute with my bank" | A forced-review rule (P1–P5) gives `human_escalation`. An approved template from the precedence table is used, with no eligibility or timing promises. A handoff brief is generated, and the queue comes from the queue-selection table. The agent sees a red "Human decision required" banner and cannot bulk-approve. |

**Frontier conditions (spec §7.5), all required:**

- the org setting is on and an admin has recorded the vendor review;
- the intent is not a security report or privacy/legal request;
- no P1–P9 terminal rule and no P0, N5 or N6 reason;
- approved, current evidence exists;
- complexity ≥ 2;
- worst-case cost ≤ $0.05 per ticket and within the daily budget;
- the residual-PII scan is clear.

**Degradation (spec §7.7).** Every stage has a time budget, and nothing fails open:

| Stage | Budget | On failure |
|---|---|---|
| PII mask | 1 s | human escalation (`pii_masking_failed`) |
| Triage | 15 s | rules baseline + human escalation (`model_unavailable`) |
| Retrieval | 1.5 s | BM25-only or vector-only |
| Local draft | 25 s | template |
| Frontier | 20 s (9 s × 2 attempts) | local draft |
| Whole pipeline | 45 s | partial result with reasons |

## 5. Policy engine

Rules are data: a versioned rule set with thresholds and seven lexicons, evaluated by pure functions (spec §7.3; [ADR-0010](adr/ADR-0010-deterministic-policy-engine-as-data.md)).

**Semantics.**

- Every rule is evaluated for every ticket; evaluation never short-circuits.
- Every fired rule is recorded with its evidence: pattern ids, scores, counts, never ticket text.
- The escalation reasons are the union of all fired rules.
- The path comes from the highest-precedence terminal rule (P1 > P2 > … > P11). P11 always fires, and P0 and N1–N7 never decide the path.
- Forced categories are **model ∪ lexicon** (recall first), and every threshold is fitted on validation data only.

| Rule | Trigger | Outcome |
|---|---|---|
| P0 (non-terminal) | Injection lexicon or Prompt Guard 2 score ≥ τ_inj | Reason `prompt_injection_suspected`; frontier off; template-only drafts |
| P1 | Customer asks for a human | Human escalation; the draft always offers a human |
| P2 | Security report (model or lexicon) | Human escalation to `security_and_privacy`; acknowledgment template, no draft |
| P3 | Privacy request or legal threat | Human escalation; legal holding template |
| P4 | Outage or matched active incident | Human escalation to `incident_response`; incident status only as a quote from the incident record |
| P5 | Refund, cancellation, duplicate charge, payment failure, chargeback | Human escalation; billing or retention holding template |
| P6 · P7 | Unsupported language · pipeline failure (masking, model, schema) | Human escalation; generic holding template |
| P8 | Low intent confidence, `other_unclear`, or missing information | Clarifying questions |
| P9 | No approved evidence ≥ τ_ret, stale-only or conflicting evidence | Human escalation with a "we'll check" template; frontier never selected |
| P10 · P11 | Complex case with every frontier condition · otherwise | Frontier draft · local draft |
| N1–N4 | Queue allow-list or low queue confidence; high churn on high value; priority floors; truncated input | Rule queue; CSM handoff draft; raise priority (never lower); `input_truncated` |
| **N5** | ≥ 8 masked PII entities | `pii_heavy_content`; frontier off |
| **N6** | P(critical) ≥ τ_crit | `critical_category_suspected`; forced human review; frontier off |
| **N7** | Medium churn with at least one churn signal | `retention_risk`; retention flag in the UI |

**Template precedence.** The draft comes from the highest-ranked fired rule:

1. P2 security acknowledgment
2. P3 legal holding
3. P4 incident status
4. P5 billing holding, or retention holding (billing wins when both apply)
5. P6/P7 generic holding
6. P9 "we'll check"

If P1 is the only fired rule, the draft is the offer-a-human template; otherwise the offer-a-human sentence is appended to whichever draft applies. P0 suppresses every model-written draft.

**Queue selection.** P2 routes to security and privacy. P3 routes there too, but only with a privacy intent. P4 routes to incident response. A lexicon-only P5 hit routes to the category's queue. Every other ticket follows the routing table after N1.

## 6. Data protection flow

```text
raw ticket --(step 0)--> PANs cut to last 4 --> AES-256-GCM envelope with the current monthly DEK --> encrypted raw text
    |                                               (enc_key_id per row; DEKs stored only wrapped by a KEK from the secret store)
    +--(step 1, worker)--> sanitize --> Presidio mask --> masked copy + encrypted placeholder map --> residual-PII gate
                                                               |
                    models, retrieval, logs, traces and the frontier only ever see the masked copy
```

- **Masking.** Presidio receives an explicit entity list. Dates, UUIDs, locations and organizations stay unmasked, because they carry entities the triage needs (charge dates, workspace ids, regions, company names). Allow-list patterns are anchored, and customer-typed placeholders are escaped first. The reversible map is encrypted with AES-256-GCM (the AAD binds ticket id, purpose and key id). It is decrypted only by the audited `reveal-pii` endpoint.
- **Retention and crypto-shred.** After 90 days the raw columns and the map are nulled. Once the newest row of a month is 90 days old, that month's DEK is destroyed and the destruction is written to a deletion ledger. Backups hold only wrapped DEKs, never the KEK, and every restore re-applies the ledger before serving traffic. A deletion request runs a `SECURITY DEFINER` purge function that covers every text column in scope ([ADR-0030](adr/ADR-0030-app-level-aes-gcm-and-crypto-shred-retention.md), [ADR-0037](adr/ADR-0037-crypto-shred-with-per-period-deks-and-deletion-ledger.md)).
- **Logs and traces.** The structlog redactor blanks credential and content keys and scrubs PII-like values, but keeps token-count fields. Ticket text is never logged. The OTel Collector enforces a fail-closed attribute allow-list.

## 7. Deployment topology

| Compose network | Members | Rule |
|---|---|---|
| `edge` | Caddy, web, API | Caddy is the only service with published ports (80/443) |
| `internal` (`internal: true`) | PostgreSQL, Redis, Ollama, API, worker, email-feed, observability | No internet route; Redis requires an ACL user and password |
| `egress` | egress-proxy | The only route to the internet; allow-list in `infra/egress-proxy/` ([ADR-0036](adr/ADR-0036-egress-allow-list-via-egress-proxy.md)) |

Today `compose.yaml` defines `internal` (`internal: true`; PostgreSQL, Redis, migrate, API) and `edge` (API). The dev override relaxes `internal` so that ports bound to 127.0.0.1 work; `egress` and the egress proxy arrive in P9.

- **Caddy edge ([ADR-0026](adr/ADR-0026-docker-compose-caddy-single-vm.md)).**
  - TLS and security headers, plus a fallback CSP for responses that set none.
  - A 3 MB global body cap, just above the largest route limit.
  - 404 for `/api/v1/metrics`, the API docs paths and `/_next/image`.
  - 405 for any non-GET/HEAD request outside `/api/*`, because there are no Server Actions.
  - Client-supplied `Content-Security-Policy`, `X-Nonce` and `X-Middleware-Subrequest` headers are stripped, and `X-Real-IP` is overwritten.
- **Same origin.** The UI and API share one origin, with no CORS in production or in development. FastAPI alone sets the cookies (`__Host-Http-tw_access`, `__Host-tw_csrf`, `__Secure-tw_refresh`). CSRF defense runs Fetch Metadata, then an Origin check, then a JSON-only rule (415 otherwise), then a signed, session-bound double-submit token (spec §12.7). The email-feed service token works only on the API's internal listener.
- **Per-route body limits (spec §11).**
  - `POST /api/v1/tickets`: 256 KB.
  - `POST /api/v1/tickets/batch`: at most 50 tickets and 2 MB.
  - KB document bodies: 1 MB.
  - Every other route: 64 KB.
  - Oversized requests get `413 PAYLOAD_TOO_LARGE` as problem+json. The P0 middleware already enforces these limits (`TW_BODY_LIMIT_*` settings).
- **Single-host deviation.** On the single-VM demo, internal hops run in plaintext on the internal bridge networks. This is a documented ASVS deviation with compensating controls. Any multi-host deployment must enable TLS.
- **Development.**
  - `docker compose up -d --build` starts the core services, with ports bound to 127.0.0.1.
  - From P8, a Caddy dev proxy at `https://localhost` puts the UI and API on one origin, as in production.
  - Until then, `pnpm dev` serves only the placeholder UI.

## 8. What exists now and what is planned

| Phase | Architecture pieces | State (2026-09-27) |
|---|---|---|
| P0 Foundation | Two uv projects; CI (lint, types, tests, integration, frontend, PR title, Compose smoke; security scans; CodeQL); Compose core services (`postgres`, `redis`, `migrate`, `api`); `create_app()` with prod-default settings, structlog redaction, RFC 9457 errors with relative URIs, request-id / security-headers / body-limit / JSON-only middleware, health endpoints; taxonomy and contracts; ports; ORM base + `0001_extensions`; research publishing; ADRs; this page | **Built** (local scaffold) |
| P1–P3 | Frozen taxonomy and JSON Schemas incl. the decoding schema; KB (112 approved + 3 adversarial docs); datasets; evaluation harness; SLM bake-off; first fine-tune; GGUF export + calibrator | Planned |
| P4 | DB schema and roles; cookie auth, CSRF and sessions; ingestion incl. the internal service-token listener; sanitizer; PII masker; period DEKs; purge function; arq worker; Ollama provider; confidence and repair; SSE | Planned |
| P5 · P6 | Hybrid retrieval in API and worker, KB workflow · policy engine, lexicons, Prompt Guard 2, drafting, citation verifier, claim guards | Planned |
| P7 | Frontier provider; handoffs, escalations and feedback; OTel, Prometheus and Grafana | Planned |
| P8 | Next.js app; `proxy.ts` nonce CSP; server-only DAL; same-origin dev proxy | Planned (placeholder UI today) |
| P9 | Networks + egress proxy; Redis ACL; Caddy edge (today's Caddyfile is an unwired placeholder); container hardening; runbooks; backups; demo host decision | Planned |
| P10 · P11 | Benchmarks with confidence intervals · public demo mode, nightly reset, v1.0.0 | Planned |

## 9. Further reading

- Decisions: [ADR index](adr/README.md), including [ADR-0022](adr/ADR-0022-arq-redis-jobs-and-sse.md) (jobs and SSE), [ADR-0033](adr/ADR-0033-citation-verifier-anchors-nli-and-claim-guards.md) (citation verifier) and [ADR-0034](adr/ADR-0034-prompt-guard-2-secondary-injection-signal.md) (injection detector).
- Security: [threat model](security/threat-model.md), [ASVS L2 checklist](security/asvs-l2-checklist.md), [audit events](security/audit-events.md).
- Research: [hybrid retrieval](research/hybrid-retrieval.md), [citation verification](research/citation-verification.md), [PII masking](research/pii-masking-presidio.md), [prompt-injection defense](research/prompt-injection-defense.md), [auth, cookies and CSRF](research/auth-cookie-jwt-csrf.md), [Next.js security](research/nextjs-security.md), [public demo deployment](research/public-demo-deployment.md).
