---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §8, §11 (tracing); spec §7.1, §11, §12.10, §12.11, §15; research observability-otel
informed: contributors; operators (runbooks)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0024: Observability with structlog, OpenTelemetry and Prometheus/Grafana; Langfuse optional

> **Amended in spec v1.1 (2026-09-27; change record A-22, A-25(i)(m)).**
> * **OTel Collector `redaction` processor with a fail-closed allow-list** (`allow_all_keys: false`): semantic-
>   convention keys plus `tw.*` attributes, and blocked-value regexes. `url.query`, `client.address`,
>   `user_agent.original` and `exception.*` are excluded. `span.record_exception()` is banned (Semgrep), and
>   `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT=1024`.
> * **Backends:** Tempo on the demo VM (single binary, local storage, 72 h retention). In dev, `grafana/otel-lgtm` or
>   **Jaeger v2** (v1 reached end of life on 2025-12-31).
> * **Prometheus metrics on internal ports only** (`api:9464`, `worker:9465`), never under `/api/v1`, with 404 at the
>   edge.
> * **Manual trace propagation into arq**, and `OTEL_SEMCONV_STABILITY_OPT_IN=http`.
> * **Langfuse is off in the public demo** (self-hosting needs about the whole demo VM). In dev it is self-hosted, or
>   Langfuse Cloud Hobby with masked data only (recorded as a third-party data flow).
> * **Redaction keys** add `set-cookie`, `x-api-key`, `api_key` and `secret`, and **token-count fields are explicitly
>   allowed** (the scaffold bug fixed in P0).
> * **Alert delivery** is Grafana alerting to e-mail or ntfy. **Security logs are kept 1 year**, with off-host
>   shipping.
> * Intra-host telemetry is plaintext under the internal-TLS deviation (ADR-0027, §12.11).

## Context and Problem Statement

The brief asks for "Langfuse or OpenTelemetry" (brief §8) and for tracing (brief §11). The spec calls for:
* structured JSON logs with request/trace ids and a hashed user id;
* OTel traces with manual pipeline spans (`pii.mask`, `triage.generate`, `retrieval.*`, `policy.evaluate`,
  `draft.generate`, `citations.verify`), propagated into arq jobs;
* Prometheus metrics (RED, pipeline, validity, decisions, tokens and cost, frontier budget and breaker, KB health,
  auth failures, rate limits, residual PII);
* five provisioned Grafana dashboards, SLOs with burn-rate alerts, and security-event alerts (§15).

Ticket text is never logged. Telemetry can still leak PII through span attributes, exception messages, URLs or
headers. v1.0 relied on an app-side allow-list only, and had no alert delivery, no retention for security logs, and
an ambiguous `/metrics` placement.

How should logs, traces, metrics and LLM observability be provided without becoming a data-leak channel?

## Decision Drivers

* Vendor-neutral instrumentation (OTel) that a reviewer can run locally.
* No telemetry egress. Telemetry stays on infrastructure we control, apart from masked-only dev Langfuse Cloud.
* **Fail-closed attribute handling at two layers** (app and Collector).
* Pipeline-stage visibility for SLOs (M-08) and diagnosis.
* Security-event visibility with alert delivery and 1-year retention (A09:2025).
* Fits the single demo VM (Langfuse excluded there).

## Considered Options

1. structlog + OTel (Collector redaction → Tempo/Jaeger v2) + Prometheus on internal ports + Grafana alerting;
   Langfuse optional and off in the demo (chosen)
2. Datadog
3. Langfuse only

## Decision Outcome

Chosen option: option 1. Configuration (spec §12.10, §15):

* **Logs:** structlog JSON (UTC) with `request_id`, `trace_id`, `span_id`, hashed `user_id`, route, status and
  latency.
  * The redaction processor blanks `password`, `token`, `authorization`, `cookie`, `set-cookie`, `x-api-key`,
    `api_key`, `secret`, `message`, `body` and `email`.
  * **Token-count keys** (`input_tokens`, `output_tokens`, `cache_*_tokens`, `total_tokens`) are allow-listed.
  * A regex scrubber runs on all string values.
  * Access logs drop the `q` search term. The JSON renderer prevents log injection.
* **Traces:**
  * OTel SDK + contrib pinned in lockstep (1.45.0 / 0.66b0 as of 2026-09-26; re-pin at P7);
  * FastAPI instrumentation (health and SSE routes excluded, header capture off), SQLAlchemy `sync_engine`, httpx,
    redis (arguments sanitized);
  * manual `traceparent` in arq jobs (`@traced_job`);
  * export: Collector (`memory_limiter` → fail-closed `redaction` → `batch` → OTLP) → Tempo (demo) / otel-lgtm or
    Jaeger v2 (dev).
* **Metrics:** `prometheus_client` via `start_http_server` on internal ports. Never mounted on the public ASGI app,
  never routed by Caddy (404 at the edge). Route-template labels only, exemplars to traces, one uvicorn worker per
  container.
* **Alerts:** Prometheus recording rules + Grafana alerting to e-mail or ntfy. Alerts cover burn rate, queue depth,
  frontier budget/breaker, stale KB, 429 spikes, CPU/disk, certificate expiry, and security events (lockouts, refresh
  reuse, CSRF failures, `pii.reveal` bursts).
* **Langfuse:** `TW_LANGFUSE_ENABLED`, off in the public demo. In dev: self-hosted, or Langfuse Cloud Hobby with
  masked data only, an isolated TracerProvider and an export-stage masking hook.
* **Retention and shipping:** security and audit events are kept 1 year and shipped off-host. The minimum is a
  nightly encrypted restic copy of audit partitions plus the deletion ledger (§12.10).
* **Request id (proposed):** an inbound `X-Request-ID` is accepted only if it matches a ULID/UUID pattern (≤ 64
  chars). Otherwise a fresh ULID is generated.

**Verify at build (research `observability-otel`):** OTel versions, whether the Collector redaction processor also
scrubs span-event attributes (unverified, so the app-level `record_exception` ban is the primary control), and
`httpx2.alias_httpx()` for tracing the anthropic SDK.

### Consequences

* Good, because two independent layers (app allow-list + Collector fail-closed allow-list) must both fail before PII
  reaches a trace backend.
* Good, because all telemetry stays on our hosts in the demo, and security events reach a human (e-mail or ntfy) and
  survive a year off-host.
* Bad, because there are several services to run (Collector, Tempo, Prometheus, Grafana, optionally Loki). They are
  internal-only, and Grafana is reached through an SSH tunnel.
* Bad, because allow-listing deliberately loses some debugging context. Masked dev Langfuse is the opt-in escape
  hatch.
* Neutral, because metric cardinality is controlled with enum labels only.

### Confirmation

* `T-SEC-LOG-redaction`:
  * with PII fixtures and secrets flowing through the pipeline, logs and exported spans contain none of them;
  * token-count keys survive;
  * a canary test shows no ticket text in spans (P7 exit).
* Collector config test: a span with a non-allow-listed attribute or a blocked value arrives stripped (proposed).
  Semgrep bans `span.record_exception()` and `str(exc)` in spans/logs.
* compose-smoke: `/api/v1/metrics` returns 404 through Caddy, and the internal ports serve metrics.
* P7 exit: a trace spans API → job → stages. Dashboards and alert rules are provisioned from committed JSON/YAML, and
  alert delivery is tested (proposed: a synthetic alert delivered at P9).
* `T-SEC-LOG-injection` (proposed): malformed `X-Request-ID` values are replaced.

## Pros and Cons of the Options

### structlog + OTel + Prometheus/Grafana (+ optional Langfuse)

* Good, because it is open, self-hosted and vendor-neutral, with no telemetry egress in the demo and fail-closed
  redaction.
* Bad, because there are several services, and redaction configuration must be maintained.

### Datadog

* Good, because it is turnkey.
* Bad, because it is SaaS: cost, lock-in, telemetry egress (residual PII risk), and reviewers can't run it.

### Langfuse only

* Good, because it is excellent for prompt and output tracing.
* Bad, because it is not general APM (no RED/SLO/security metrics), it concentrates the most sensitive content, and it
  doesn't fit on the demo VM.

## More Information

* Spec (private): §7.1 (observability line), §11 (metrics not an API route), §12.10 (redaction, retention, off-host
  shipping, alert delivery), §12.11 (plaintext intra-host telemetry), §15. Change record A-22, A-25 (i)(m).
* Brief (private): §8, §11. BR-036, BR-060.
* Research: [observability-otel](../research/observability-otel.md).
* Related ADRs: ADR-0019, ADR-0022, ADR-0026, ADR-0027 (TLS deviation).
* Security docs: [audit events](../security/audit-events.md).
* Revisit when: the demo needs external uptime monitoring, or telemetry volume outgrows the VM.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (Collector redaction allow-list,
  Tempo/Jaeger v2, internal Prometheus ports, Langfuse off in the demo, alert delivery, 1-year security logs).
