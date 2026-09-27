# Observability: OpenTelemetry, Prometheus, Tempo/Jaeger, Langfuse - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Resolved. Package set, propagation design, Collector/Tempo/Prometheus configs and the Langfuse decision are all defined. Exact versions must be re-pinned at P7 (see "To verify").
**Category**: Operations / Observability
**Linked ADR(s)**: ADR-0024 (structlog + OTel + Prometheus/Grafana; Langfuse optional); related ADR-0022 (arq), ADR-0026 (deployment), ADR-0027 (ASVS)
**Spec sections**: §7.1 (observability line), §12.10 (logging redaction, span allow-list), §14.1 (`core/telemetry.py`, `infra/otel/collector.yaml`), §15 (logs, traces, metrics, dashboards, SLOs), §16 P7, §23

---

## EXECUTIVE SUMMARY

- **Traces.**
  - Use the OpenTelemetry Python SDK **1.45.0** with contrib instrumentations **0.66b0** (all released 2026-09-25): `opentelemetry-instrumentation-fastapi`, `-sqlalchemy` (instrument `engine.sync_engine` for the async engine), `-httpx` and `-redis` (covers `redis.asyncio`, and sanitises command arguments to `CMD ? ?` by default).
  - Contrib has **no arq instrumentation**. W3C `traceparent` is therefore injected into the job kwargs at enqueue time and extracted in a small decorator on each worker task (snippet in D3).
- **Collector.**
  - Use `otel/opentelemetry-collector-contrib` **0.161.0**. The traces pipeline is `otlp` receiver → `memory_limiter` → `redaction` (fail-closed attribute allow-list, which implements spec §12.10) → `batch` → `otlp_grpc` exporter to Tempo.
  - In current Collector releases the gRPC and HTTP OTLP exporters are `otlp_grpc` and `otlp_http`; `otlp`/`otlphttp` remain only as deprecated aliases.
- **Trace backend.**
  - **Demo VM:** Tempo **3.0.3** (single binary, local storage, short retention) viewed in Grafana, which the spec already needs for dashboards.
  - **Dev:** `grafana/otel-lgtm`, a one-container Collector + Prometheus + Tempo + Loki + Grafana stack intended for dev/demo/testing. Alternatively **Jaeger v2** all-in-one (`cr.jaegertracing.io/jaegertracing/jaeger:2.21.0`, in-memory storage).
  - **Jaeger v1 reached end of life on 2025-12-31.** Do not use `1.x` images.
- **Metrics.**
  - Keep **`prometheus_client` 0.26.0** for the §15 metric names (pull model, exact names, exemplars). Serve them on an **internal-only port**, not on the public API app.
  - Use OTel for traces only. OTel metrics → Prometheus would rename metrics with unit/`_total` suffixes and add moving parts, for no gain at this scale.
- **Logs.**
  - structlog **26.1.0** JSON to stdout, with a processor that adds `trace_id`/`span_id` via `opentelemetry.trace.format_trace_id`. Redaction runs **before** rendering or any exporter.
  - Optional: `opentelemetry-instrumentation-structlog` (0.66b0) can emit the same events as OTel logs to the Collector (→ Loki).
- **Langfuse.**
  - Self-hosting needs web + worker + Postgres + **ClickHouse** + Redis/Valkey + S3-compatible storage. Langfuse recommends **at least 4 cores / 16 GiB RAM / 100 GiB disk** for its docker-compose VM option, and notes compose lacks HA and backups. It **cannot share the 8 vCPU / 16 GB demo VM**.
  - Decision: **off in the public demo**. Optional in dev (self-hosted on the laptop) or via Langfuse Cloud Hobby (free: 50k units/month, 30-day data access, 2 users) with masked data only.
  - The SDK (4.15.6) gets an **isolated TracerProvider** and the export-stage `mask_otel_spans` hook.
- **Spec impacts: 8 items** (see SPEC IMPACT). The main ones: Langfuse on the demo VM, `/metrics` exposure, the arq pickle serialiser, and the missing arq instrumentation.

---

## QUESTIONS

1. Which OTel Python packages instrument FastAPI, SQLAlchemy (async), httpx and redis today? At what versions?
2. How do we propagate trace context from the API into arq jobs?
3. What should the Collector configuration be (receivers, processors incl. PII allow-list, exporters)?
4. Tempo or Jaeger for dev, and what for the demo VM?
5. Prometheus client library or OTel metrics?
6. What does self-hosting Langfuse require, and how does masking work?
7. How do we correlate structlog JSON logs with traces (trace_id/span_id)?
8. (Derived) How do we keep ticket text and PII out of all telemetry (spec §12.10, ASVS V16.2.5)?

---

## FINDINGS

### F1. Versions (PyPI JSON API and GitHub releases, accessed 2026-09-26)

| Component | Latest | Date | Notes |
|---|---|---|---|
| `opentelemetry-api` / `-sdk` / `-exporter-otlp(-proto-grpc/-http)` | 1.45.0 | 2026-09-25 | Python >= 3.10 |
| `opentelemetry-instrumentation-{fastapi,sqlalchemy,httpx,redis,asyncpg,logging,structlog}` | 0.66b0 | 2026-09-25 | Beta ("b0") line |
| `opentelemetry-exporter-prometheus` | 0.66b0 | 2026-09-25 | Not used (see D6) |
| `structlog` | 26.1.0 | 2026-06-06 | |
| `prometheus-client` | 0.26.0 | 2026-07-24 | |
| `arq` | 0.28.0 | 2026-04-16 | |
| `langfuse` (Python SDK) | 4.15.6 | 2026-09-24 | Server: `langfuse/langfuse` v4.46.0 (2026-09-25) |
| OTel Collector (core/contrib releases) | v0.161.0 | 2026-09-15/16 | |
| Grafana Tempo | v3.0.3 (v3.1.0-rc.1 pre-release) | 2026-08-13 | Tempo 3.0.0 released 2026-05-28 |
| Jaeger | v2.21.0 | 2026-09-14 | v1 end of life 2025-12-31 |
| Prometheus | v3.15.0 | 2026-09-25 | |
| Grafana | v13.2.2 | 2026-09-15 | |
| Loki (optional) | v3.7.8 | 2026-09-17 | |

### F2. Instrumentation specifics (opentelemetry-python-contrib docs and source, accessed 2026-09-26)

- **FastAPI.**
  - `FastAPIInstrumentor.instrument_app(app, excluded_urls=..., server_request_hook=..., tracer_provider=..., meter_provider=..., http_capture_headers_server_request=..., http_capture_headers_sanitize_fields=..., exclude_spans=[...])`.
  - Environment equivalents: `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` and `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_*`.
  - **Header capture is off by default.** Keep it off, because cookies and CSRF tokens would otherwise leak.
- **SQLAlchemy (async).** Instrument the sync core of the async engine: `SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)`. Options: `enable_commenter` / `commenter_options` (sqlcommenter) and `enable_attribute_commenter`. With bound parameters the SQL text carries placeholders, not values. Use either SQLAlchemy or asyncpg instrumentation, not both, to avoid duplicate spans.
- **httpx.** `HTTPXClientInstrumentor().instrument()` (global) or `instrument_client(client)` for a specific `AsyncClient`. Async request/response hooks are available. `OTEL_PYTHON_HTTPX_EXCLUDED_URLS` excludes URLs.
- **redis.** `RedisInstrumentor().instrument()` also instruments `redis.asyncio` clients. The source (`util._format_command_args`) sanitises arguments to `COMMAND ? ?` and caps the length at 1000 characters. There is a `valkey-py` instrumentation too.
- **Semantic conventions.** HTTP (and DB) instrumentations honour `OTEL_SEMCONV_STABILITY_OPT_IN`: `http` emits only stable names, `http/dup` emits both. **The default is still the old experimental names.**
- **No arq instrumentation.** The contrib `instrumentation/` tree (53 entries) has celery, remoulade and aio-pika, but **no arq**.
- **structlog instrumentation.** The new `opentelemetry-instrumentation-structlog` provides a `StructlogProcessor` that turns each structlog event into an OTel `LogRecord`, including trace context. It exports logs; it does not add IDs to stdout JSON.
- **AnyIO.** `anyio.to_thread.run_sync` copies the current context into the worker thread, so spans started inside the thread parent correctly. asyncio tasks (the `TaskGroup` in §7.2) also inherit the context when they are created.

### F3. arq facts (docs v0.28.0 and source, accessed 2026-09-26)

- `ArqRedis.enqueue_job(function, *args, _job_id=None, _queue_name=None, _defer_until=None, _defer_by=None, _expires=None, _job_try=None, **kwargs)`. It returns `Job` or `None` (`None` means a job with that id already exists).
- Worker functions receive `ctx` (containing `job_id`, `job_try`, `enqueue_time` and `redis`) followed by the job's args and kwargs. `WorkerSettings` has `on_startup`, `on_shutdown`, `on_job_start`, `on_job_end`, `after_job_end`, `max_jobs`, `job_timeout`, `max_tries`, `keep_result`, `job_serializer` and `job_deserializer`. The docs warn that jobs may run more than once, so tasks must be idempotent.
- **Default serialisation is `pickle`** (`arq/jobs.py`). The docs show a msgpack alternative for both `create_pool(..., job_serializer=, job_deserializer=)` and `WorkerSettings`.

### F4. Collector components (collector / collector-contrib READMEs at v0.161.0, accessed 2026-09-26)

- `otlp` receiver: gRPC on 4317, HTTP on 4318.
- `memory_limiter` (beta for traces/metrics/logs): `check_interval`, plus `limit_mib`/`spike_limit_mib` or percentage variants. The suggested spike is about 20% of the limit. It must run first.
- `batch` (beta): defaults `send_batch_size` 8192 and `timeout` 200 ms. It goes after memory_limiter and any sampling. Exporters can also batch inside `sending_queue` (`batch: {}`), which is off by default.
- `redaction` (contrib; **beta for traces**, alpha for logs/metrics):
  - It deletes attributes not listed in `allowed_keys`. It is fail-closed: an empty list removes everything, unless `allow_all_keys: true`.
  - It masks values matching `blocked_values` regexes, and `blocked_key_patterns` masks by key name.
  - `summary: debug|info|silent` controls the diagnostic attributes it adds.
  - `url_sanitizer` is available.
- **Exporter naming.** The OTLP/HTTP exporter README (v0.161.0) says `otlphttp` is a deprecated alias of `otlp_http`. The gRPC exporter's examples use `otlp_grpc`. At v0.140.0 the names were still `otlp`/`otlphttp`.
- `debug` exporter: `verbosity: basic|normal|detailed`.

### F5. Backends (accessed 2026-09-26)

- **Tempo 3.0** (released 2026-05-28):
  - Completes the move to the new ingest/write architecture and removes deprecated 2.x components (legacy ingesters, v2 blocks, the OpenCensus receiver, etc.).
  - TraceQL metrics are GA, and trace redaction support was added.
  - Single-binary mode can run without Kafka for small deployments.
  - The v3.0.3 single-binary example uses the `local` storage backend.
  - The configuration reference lists `block_retention` (default 336 h) in the compaction block.
- **Jaeger v2** (Nov 2024) is built on the OTel Collector and ships a single binary. The all-in-one image `cr.jaegertracing.io/jaegertracing/jaeger:2.21.0` exposes the UI on 16686 and OTLP on 4317/4318, with transient in-memory storage. GitHub issue #6321 fixed Jaeger 1.x end of life at 2025-12-31, with no v1 releases from 2026-01-01.
- **`grafana/otel-lgtm`** bundles Collector, Prometheus, Tempo, Loki, Pyroscope and Grafana. It is described as intended for development, demo and testing environments, not production.
- **Prometheus 3.x:**
  - An OTLP receiver is available behind `--web.enable-otlp-receiver`, at `/api/v1/otlp/v1/metrics`. Translation strategies control suffixing and UTF-8 handling.
  - Exemplar storage is still behind `--enable-feature=exemplar-storage`.
  - `prometheus_client` multiprocess mode needs `PROMETHEUS_MULTIPROC_DIR` wiped between runs. It does not support custom collectors, Info/Enum, exemplars or `pid` labels. Avoid it by running one process per container.

### F6. Langfuse (docs, accessed 2026-09-26)

- **Self-hosted architecture:** Langfuse Web plus Langfuse Worker, with Postgres (transactional), **ClickHouse** (traces/analytics), Redis/Valkey (queue/cache) and S3/blob storage (events, media).
- **Docker compose** is positioned for testing or single-VM use without HA, scaling or backups. For a VM the docs recommend **>= 4 cores and 16 GiB memory** (e.g., AWS t3.xlarge) and about **100 GiB** of storage. Kubernetes/Helm or cloud templates are recommended for production. Some add-on features need a licence key.
- **Cloud plans** (pricing page):
  - Hobby: free, 50k units/month, 30-day data access, 2 users.
  - Core: $29/month, 100k units, 90 days.
  - Pro: $199/month.
  - Enterprise: $2,499/month.
  - Regions: US/EU/Japan (plus HIPAA US on Enterprise). Overage from $8 per 100k units.
- **SDK and OTel.**
  - By default Langfuse attaches its span processor to the **global** TracerProvider. Passing `Langfuse(tracer_provider=TracerProvider())` isolates it (spans across providers do not nest).
  - v4 applies a default export filter: Langfuse-SDK spans, `gen_ai.*` spans and known LLM instrumentation scopes. `should_export_span` customises it, and `blocked_instrumentation_scopes` is deprecated.
  - Third-party spans without the project key "can be sent to all projects". That is a reason to isolate the provider.
- **Masking.**
  - The legacy `mask=` hook applies to Langfuse-SDK attributes only.
  - The recommended **`mask_otel_spans=`** hook (changelog 2026-06-16, "export-stage masking") receives the raw span attributes of all spans exported by that client, including third-party ones, and returns sparse patches (set/delete attributes).
  - Both run client-side, before data leaves the process.

---

## DECISION / RECOMMENDATION

### D1. Topology

```
api (FastAPI) ──OTLP/gRPC──┐                       ┌─> tempo:4317 (traces) ─> Grafana (Tempo DS)
worker (arq)  ──OTLP/gRPC──┼─> otel-collector ─────┤
email-feed    ──OTLP/gRPC──┘  memory_limiter →     └─> debug (dev only)
                              redaction → batch
Prometheus ──scrape──> api:9464/metrics, worker:9465/metrics (internal ports; never routed by Caddy)
stdout JSON logs (structlog, trace_id/span_id) ─> docker logs (→ Loki optional)
Langfuse: disabled in the public demo; dev/Cloud only, isolated provider + mask_otel_spans
```

### D2. Pinned packages (backend `pyproject.toml`, re-verify at P7)

```toml
"opentelemetry-api==1.45.0", "opentelemetry-sdk==1.45.0",
"opentelemetry-exporter-otlp-proto-grpc==1.45.0",
"opentelemetry-instrumentation-fastapi==0.66b0", "opentelemetry-instrumentation-sqlalchemy==0.66b0",
"opentelemetry-instrumentation-httpx==0.66b0", "opentelemetry-instrumentation-redis==0.66b0",
"structlog==26.1.0", "prometheus-client==0.26.0", "arq==0.28.0", "msgpack",   # msgpack version: pin at P0
# optional
"opentelemetry-instrumentation-structlog==0.66b0", "langfuse==4.15.6",
```

The API (1.x) and contrib (0.xb0) versions move in lockstep. Upgrade them together, never individually.

### D3. `core/telemetry.py`: init, instrumentation, manual spans, arq propagation

```python
# backend/src/ticketward/core/telemetry.py
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

_EXCLUDED = "health/live,health/ready,tickets/[^/]+/events"   # comma-separated regexes; SSE streams excluded


def init_tracing(service_name: str) -> TracerProvider:
    # Resource/sampler/exporter also read OTEL_* env vars (OTEL_RESOURCE_ATTRIBUTES, OTEL_TRACES_SAMPLER,
    # OTEL_EXPORTER_OTLP_ENDPOINT); explicit service.name wins.
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))   # endpoint from env
    trace.set_tracer_provider(provider)
    return provider


def instrument_api(app, async_engine) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED)       # header capture stays OFF
    instrument_common(async_engine)


def instrument_common(async_engine) -> None:
    SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
    HTTPXClientInstrumentor().instrument()                                 # Ollama, Anthropic SDK (httpx)
    RedisInstrumentor().instrument()                                       # includes redis.asyncio; args sanitised


tracer = trace.get_tracer("ticketward")

# ---- API side: enqueue with W3C context -------------------------------------------------
async def enqueue_traced(pool, function: str, *args: str, job_id: str, request_id: str) -> str | None:
    carrier: dict[str, str] = {}
    with tracer.start_as_current_span(f"{function} send", kind=SpanKind.PRODUCER,
                                      attributes={"messaging.system": "arq", "messaging.operation.type": "send",
                                                  "messaging.destination.name": "arq:queue"}):
        propagate.inject(carrier)                                  # traceparent / tracestate
        job = await pool.enqueue_job(function, *args, _job_id=job_id, otel=carrier, request_id=request_id)
    return job.job_id if job else None                             # None = duplicate job id (idempotent)

# ---- Worker side: decorator for every arq task ------------------------------------------
import functools
import structlog

def traced_job(fn):
    @functools.wraps(fn)
    async def wrapper(ctx, *args, otel: dict[str, str] | None = None, request_id: str | None = None, **kwargs):
        parent = propagate.extract(otel or {})
        structlog.contextvars.bind_contextvars(job_id=ctx["job_id"], job_try=ctx["job_try"], request_id=request_id)
        with tracer.start_as_current_span(f"{fn.__name__} process", context=parent, kind=SpanKind.CONSUMER,
                                          attributes={"messaging.system": "arq", "messaging.operation.type": "process",
                                                      "messaging.message.id": ctx["job_id"]}) as span:
            try:
                return await fn(ctx, *args, **kwargs)
            except Exception as exc:
                span.set_attribute("error.type", type(exc).__name__)   # never record str(exc): may contain PII
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                structlog.contextvars.clear_contextvars()
    return wrapper

# Usage: @traced_job async def process_ticket(ctx, ticket_id: str) -> None: ...
```

Worker settings, which also carry the ASVS 1.5.2 fix:

```python
import msgpack
from functools import partial

class WorkerSettings:
    functions = [process_ticket, redraft]
    job_serializer = msgpack.packb
    job_deserializer = partial(msgpack.unpackb, raw=False)     # job args AND return values must be msgpack primitives
                                                               # (str ids, carrier dict, None); no UUID/datetime objects
    max_jobs = 2                                               # spec §12.2 (CPU SLM)
    on_startup = worker_startup     # init_tracing("tw-worker"); instrument_common(engine); start_http_server(9465)
    on_shutdown = worker_shutdown   # provider.shutdown() to flush spans
# create_pool(..., job_serializer=msgpack.packb, job_deserializer=partial(msgpack.unpackb, raw=False)) on the API side
```

Rules for manual spans:

- Use the spec's names (`pii.mask`, `triage.generate`, `retrieval.bm25`, `retrieval.vector`, `retrieval.rerank`, `policy.evaluate`, `draft.generate`, `citations.verify`).
- Attributes may only be ids, counts, scores, model/provider names, versions, token counts, cost and decision enums. Never ticket text, prompts, chunk text or entity values.
- `span.record_exception()` is **banned** in pipeline code, because the message and stack may contain PII. Enforce this with a Semgrep rule.

### D4. structlog correlation and redaction order

```python
# backend/src/ticketward/core/logging.py
import logging
import structlog
from opentelemetry import trace


def add_otel_ids(_logger, _method, event_dict):
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = trace.format_trace_id(ctx.trace_id)   # 32 hex chars, matches Tempo/Jaeger
        event_dict["span_id"] = trace.format_span_id(ctx.span_id)
    return event_dict


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,             # request_id, user_id_hash, ticket_id, job_id
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),  # ASVS 16.2.2 UTC
            add_otel_ids,
            structlog.processors.format_exc_info,               # render tracebacks BEFORE scrubbing them
            redact_processor,                                   # §12.10 key redaction + regex PII scrub (fail-closed)
            # optional: StructlogProcessor() from opentelemetry-instrumentation-structlog goes HERE (after redaction)
            structlog.processors.JSONRenderer(),                # JSON escaping prevents log injection (ASVS 16.4.1)
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
```

Do not rely on `StructlogInstrumentor().instrument()` to place its processor. Its placement relative to redaction is **UNVERIFIED**. Add `StructlogProcessor()` explicitly after `redact_processor` if OTel log export is enabled.

### D5. Collector config (`infra/otel/collector.yaml`, otelcol-contrib 0.161.0)

```yaml
receivers:
  otlp:
    protocols:
      grpc: { endpoint: 0.0.0.0:4317 }      # internal network only; no published port
      http: { endpoint: 0.0.0.0:4318 }

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 400                          # container limit 512M
    spike_limit_mib: 80
  redaction/traces:
    allow_all_keys: false                   # fail closed: unknown attributes are dropped
    allowed_keys:
      # HTTP (stable + legacy names; confirm with the debug exporter which set is emitted)
      - http.request.method
      - http.response.status_code
      - http.route
      - url.path
      - url.scheme
      - server.address
      - server.port
      - network.protocol.version
      - error.type
      - http.method
      - http.status_code
      - http.scheme
      - http.host
      - net.host.port
      # DB / cache (SQL text uses bound parameters; redis args are pre-sanitised)
      - db.system
      - db.system.name
      - db.name
      - db.namespace
      - db.operation
      - db.operation.name
      - db.statement
      - db.query.text
      - db.redis.database_index
      # messaging (arq)
      - messaging.system
      - messaging.operation.type
      - messaging.message.id
      - messaging.destination.name
      # Ticketward allow-list (ids, counts, scores, enums only)
      - tw.ticket_id
      - tw.stage
      - tw.decision
      - tw.policy_version
      - tw.model
      - tw.provider
      - tw.tokens.input
      - tw.tokens.output
      - tw.cost_usd
      - tw.retrieval.k
      - tw.retrieval.top_score
      - tw.validity
      - tw.escalation_reasons
    blocked_values:
      - "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"   # email
      - "\\b(?:\\d[ -]*?){13,19}\\b"                        # card-like numbers
      - "tm_live_[A-Za-z0-9]+"                              # fictional Taskmoor API keys (spec §12.5)
    summary: info
  batch:
    timeout: 1s
    send_batch_size: 1024

exporters:
  otlp_grpc/tempo:                           # 'otlp' is a deprecated alias in current releases
    endpoint: tempo:4317
    tls: { insecure: true }                  # intra-host plaintext = documented ASVS 12.3 deviation
  debug:
    verbosity: basic

extensions:
  health_check: { endpoint: 0.0.0.0:13133 }

service:
  extensions: [health_check]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, redaction/traces, batch]
      exporters: [otlp_grpc/tempo]           # add debug in dev only
```

Deliberately excluded:

- `url.query` / `http.url` / `http.target` (search terms can hold PII).
- `client.address` and `user_agent.original` (personal data).
- `exception.message` / `exception.stacktrace`.

Whether the redaction processor also scrubs **span-event** attributes is **UNVERIFIED**. The app-level ban on `record_exception` (D3) is the primary control.

### D6. Metrics: `prometheus_client`, not OTel metrics

| Criterion | `prometheus_client` | OTel metrics SDK → Collector → Prometheus |
|---|---|---|
| Exact §15 names (`tw_*_total`, `_seconds`) | Yes | Translation adds or changes suffixes unless a strategy is configured |
| Moving parts | Scrape only | SDK reader + OTLP + Collector/Prometheus OTLP receiver |
| Exemplars (metric → trace) | Yes (OpenMetrics; Prometheus `exemplar-storage` flag) | Possible, more config |
| Multi-process caveats | Avoid multiprocess mode: 1 uvicorn worker per container | None |

Decision: `prometheus_client` served on **internal ports** (`api:9464`, `worker:9465`) via `start_http_server`. Never mount it on the public ASGI app. Label with route **templates** (`request.scope["route"].path`), never raw paths, to cap cardinality.

```yaml
# infra/prometheus/prometheus.yml
global: { scrape_interval: 15s }
scrape_configs:
  - job_name: tw-api
    static_configs: [{ targets: ["api:9464"] }]
  - job_name: tw-worker
    static_configs: [{ targets: ["worker:9465"] }]
# Prometheus flags: --storage.tsdb.retention.time=7d --enable-feature=exemplar-storage
```

### D7. Trace backend: dev vs demo

| Option | Footprint | UI | Storage | Use |
|---|---|---|---|---|
| **`grafana/otel-lgtm`** (dev default) | 1 container | Grafana (traces, metrics, logs together) | Ephemeral/dev | Local development; parity with the demo's Grafana UX |
| **Jaeger v2 all-in-one** (dev alternative) | 1 container | Jaeger UI :16686 | In-memory | Quick trace-only debugging |
| **Tempo 3.0.3 + Grafana** (demo VM) | 2 containers (+ Prometheus) | Grafana (TraceQL) | Local disk, 72 h | Public demo, "traces visible end to end" (P7 exit) |

```yaml
# infra/tempo/tempo.yaml  (adapted from the Tempo v3.0.3 single-binary example)
stream_over_http_enabled: true
server: { http_listen_port: 3200, log_level: info }
distributor:
  receivers:
    otlp:
      protocols:
        grpc: { endpoint: "0.0.0.0:4317" }
storage:
  trace:
    backend: local
    wal: { path: /var/tempo/wal }
    local: { path: /var/tempo/blocks }
compaction:
  block_retention: 72h        # key and placement per the current config reference; VERIFY against Tempo 3.x at build
usage_report: { reporting_enabled: false }
# metrics_generator (span metrics/service graphs -> Prometheus remote write) left OFF on the 16 GB VM
```

Grafana and Tempo are **not published publicly**. Reach them via an SSH tunnel or Tailscale (see `public-demo-deployment.md`).

### D8. Environment (compose.prod.yaml excerpt)

```yaml
x-otel-env: &otel-env
  OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
  OTEL_EXPORTER_OTLP_PROTOCOL: grpc
  OTEL_TRACES_SAMPLER: parentbased_always_on      # low demo traffic; switch to parentbased_traceidratio if needed
  OTEL_RESOURCE_ATTRIBUTES: deployment.environment.name=demo,service.version=${GIT_SHA}   # semconv key: verify
  OTEL_SEMCONV_STABILITY_OPT_IN: http             # stable HTTP names (default is still the old ones)
  OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT: "1024"
  OTEL_METRICS_EXPORTER: none                     # metrics via prometheus_client
  OTEL_LOGS_EXPORTER: none                        # unless OTel log export is enabled
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.161.0     # pin by digest at P7
    command: ["--config=/etc/otelcol/collector.yaml"]
    deploy: { resources: { limits: { memory: 512M } } }
    networks: [internal]
  tempo:
    image: grafana/tempo:3.0.3
    deploy: { resources: { limits: { memory: 768M } } }
    networks: [internal]
```

Memory limits are **estimates (UNVERIFIED)**. Measure at P9 and record them in `system-status.md`.

### D9. Langfuse (optional; `TW_LANGFUSE_ENABLED`)

- **Public demo: `TW_LANGFUSE_ENABLED=false`.** Self-hosting needs about 4 cores / 16 GiB / 100 GiB, which is the entire demo VM.
- **Dev:** run Langfuse's docker compose on the laptop, or use **Langfuse Cloud Hobby** (free tier as of the access date). If Cloud is used, record it as a third-party data flow (ASVS 14.2.3): synthetic, masked prompts only.
- **Wiring** (SDK 4.15.6; the mask types' import path is **UNVERIFIED — check at P7**):

```python
from opentelemetry.sdk.trace import TracerProvider
from langfuse import Langfuse

def init_langfuse(settings):
    if not settings.langfuse_enabled:
        return None
    return Langfuse(
        tracer_provider=TracerProvider(),        # isolated: FastAPI/SQL/httpx spans never reach Langfuse
        mask_otel_spans=scrub_langfuse_spans,    # export-stage patch: run the same regex PII scrubber on every str attribute
    )                                            # keep the default LLM-focused should_export_span filter
```

- **Masking is defense in depth.** The primary control stays upstream: Presidio masks the text before any model call, so prompts sent to Langfuse are already masked (spec §12.4 LLM02).

### D10. Dashboards and alerts (links to spec §15)

- Provision Grafana datasources (Prometheus, Tempo) and the five dashboards as JSON in `infra/grafana/`.
- Burn-rate alerts use Prometheus recording rules on `tw_http_requests_total`.
- Add an exemplar link from `tw_http_request_duration_seconds` to Tempo.

---

## SPEC IMPACT

Disposition in spec v1.1: every item below was applied (A-22; ADR-0022 and ADR-0024 amended).

| # | Spec location | Finding | Recommendation |
|---|---|---|---|
| SI-O1 | §15 "Langfuse is optional"; §16 P11 single 16 GB VM | Langfuse self-host (compose) recommends >= 4 cores / 16 GiB / 100 GiB, plus ClickHouse, S3 and Redis; it cannot co-reside with the app | Off in the public demo; dev-only self-host or Cloud Hobby with masked data; document the third-party flow |
| SI-O2 | §11 `GET /metrics` "internal network only" under base `/api/v1`, next to public `GET /metrics/ops` | Same path namespace as a public route; accidental exposure risk (ASVS 13.4.5) | Serve Prometheus on internal ports 9464/9465 (not on the ASGI app, not routed by Caddy) |
| SI-O3 | §15 "Trace context is propagated into arq jobs" | No arq instrumentation exists in opentelemetry-python-contrib | Manual `propagate.inject`/`extract` design (D3) |
| SI-O4 | ADR-0022 / §7.1 arq | arq's default job serialiser is `pickle` (ASVS 1.5.2) | msgpack serialiser on both producer and worker |
| SI-O5 | §15 "Tempo (or Jaeger in dev)" | Jaeger v1 is EOL (2025-12-31) | Specify Jaeger **v2** if Jaeger is used; recommend `grafana/otel-lgtm` as the dev default |
| SI-O6 | §12.10 "OTel span attributes follow the same allow-list" | Needs a concrete mechanism | Collector `redaction` processor (fail-closed `allowed_keys`) + ban `record_exception` + attribute length limit |
| SI-O7 | §15 metrics list | OTel defaults still emit old HTTP semconv names | Set `OTEL_SEMCONV_STABILITY_OPT_IN=http`; keep §15 names through prometheus_client |
| SI-O8 | §12.9 internal network | OTLP to Collector/Tempo and Prometheus scrapes are plaintext intra-host | Record under the ASVS 12.3.x deviation (see `owasp-asvs-l2.md` SI-S5) |

---

## IMPLEMENTATION CHECKLIST (P7 unless noted)

- [ ] Pin the D2 packages (lockstep OTel versions) and images by digest; Dependabot groups for `opentelemetry-*`.
- [ ] `core/telemetry.py` + `core/logging.py` (D3/D4); call them in the API lifespan and in the worker `on_startup`/`on_shutdown`.
- [ ] `@traced_job` on all arq tasks; `enqueue_traced` everywhere; msgpack serialisers on both sides (P4).
- [ ] Manual spans for the eight pipeline stages with allow-listed attributes; Semgrep rule banning `record_exception` and `str(exc)` in span/log calls.
- [ ] `infra/otel/collector.yaml`, `infra/tempo/tempo.yaml`, `infra/prometheus/prometheus.yml`, Grafana provisioning.
- [ ] Dev: `grafana/otel-lgtm` service under the compose `observability` profile (Jaeger v2 as an alternative profile).
- [ ] prometheus_client registry + `start_http_server` on 9464/9465; route-template labels; exemplars.
- [ ] Tests:
  - redaction unit tests (log processor);
  - an integration test that a span from the pipeline carries **no** ticket text: run a stub ticket with a known canary string, export via the `debug` exporter, and grep for the canary;
  - a trace-continuity test (API span → worker span share `trace_id`).
- [ ] P9: measure container memory; tune `memory_limiter` and the limits.
- [ ] Optional: Langfuse wiring behind `TW_LANGFUSE_ENABLED` (off by default).

---

## OPEN RISKS / TO VERIFY

- **Versions move monthly.** OTel Python ships roughly monthly and the Collector every two weeks. Re-pin at P7 and keep API, SDK and contrib in lockstep.
- **Semantic-convention key names** (`deployment.environment.name`, stable HTTP/DB names) and the redaction allow-list must be validated against real exported spans (debug exporter). **Verify at build.**
- **Tempo 3.x retention key placement** (`compaction.block_retention`) and single-binary behaviour without Kafka. **Verify against the Tempo 3.x docs and examples at build.**
- **Redaction processor coverage of span-event attributes: UNVERIFIED.**
- **Langfuse SDK v4 API** (`mask_otel_spans` types, `should_export_span` signature) is new (2026). **Verify at P7.**
- **`opentelemetry-instrumentation-structlog`** is beta (0.66b0). Its automatic processor placement is **UNVERIFIED**.
- **Resource figures** for Collector, Tempo, Prometheus and Grafana are estimates. **UNVERIFIED until measured.**

---

## LINKED ADR

- **ADR-0024** (Observability): add the Collector processors, Tempo for the demo, `grafana/otel-lgtm`/Jaeger v2 for dev, prometheus_client on internal ports, Langfuse off in the demo.
- **ADR-0022** (arq): msgpack serialiser + manual trace propagation.

---

## SOURCES (all accessed 2026-09-26)

- PyPI JSON API (`https://pypi.org/pypi/<package>/json`) for opentelemetry-* 1.45.0 / 0.66b0, structlog 26.1.0, prometheus-client 0.26.0, arq 0.28.0, langfuse 4.15.6
- [opentelemetry-python-contrib instrumentation directory](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation) (no arq; structlog, valkey present)
- OTel contrib docs: [FastAPI](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html), [SQLAlchemy](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html), [httpx](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/httpx/httpx.html), [redis](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/redis/redis.html); [redis util source (`_format_command_args`)](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/instrumentation/opentelemetry-instrumentation-redis/src/opentelemetry/instrumentation/redis/util.py); [structlog instrumentation source](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/instrumentation/opentelemetry-instrumentation-structlog/src/opentelemetry/instrumentation/structlog/__init__.py)
- [OTEL_SEMCONV_STABILITY_OPT_IN documentation issue #4202](https://github.com/open-telemetry/opentelemetry-python-contrib/issues/4202)
- [opentelemetry-api `format_trace_id` (span.py)](https://github.com/open-telemetry/opentelemetry-python/blob/main/opentelemetry-api/src/opentelemetry/trace/span.py)
- [AnyIO: working with threads (context propagation)](https://anyio.readthedocs.io/en/stable/threads.html)
- [arq docs v0.28.0](https://arq-docs.helpmanual.io/); [arq `enqueue_job`/`create_pool` source](https://github.com/python-arq/arq/blob/v0.28.0/arq/connections.py); [arq jobs.py (pickle default)](https://github.com/python-arq/arq/blob/v0.28.0/arq/jobs.py); [msgpack example](https://github.com/python-arq/arq/blob/v0.28.0/docs/examples/custom_serialization_msgpack.py)
- Collector READMEs (v0.161.0): [otlp_http exporter (deprecated alias note)](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.161.0/exporter/otlphttpexporter/README.md), [otlp_grpc exporter](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.161.0/exporter/otlpexporter/README.md), [batch processor](https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/batchprocessor/README.md), [memory_limiter](https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/memorylimiterprocessor/README.md), [exporterhelper (sending_queue batch)](https://github.com/open-telemetry/opentelemetry-collector/blob/main/exporter/exporterhelper/README.md), [redaction processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/redactionprocessor/README.md)
- GitHub releases API: [collector-releases](https://github.com/open-telemetry/opentelemetry-collector-releases/releases), [tempo](https://github.com/grafana/tempo/releases), [jaeger](https://github.com/jaegertracing/jaeger/releases), [prometheus](https://github.com/prometheus/prometheus/releases), [grafana](https://github.com/grafana/grafana/releases), [langfuse](https://github.com/langfuse/langfuse/releases)
- [Tempo v3.0.0 release notes](https://github.com/grafana/tempo/releases/tag/v3.0.0); [Tempo v3.0.3 single-binary example](https://github.com/grafana/tempo/blob/v3.0.3/example/docker-compose/single-binary/tempo.yaml); [Tempo configuration reference](https://grafana.com/docs/tempo/latest/configuration/)
- [Jaeger getting started (v2.21)](https://www.jaegertracing.io/docs/latest/getting-started/); [Jaeger v1 end-of-life issue #6321](https://github.com/jaegertracing/jaeger/issues/6321)
- [grafana/docker-otel-lgtm README](https://github.com/grafana/docker-otel-lgtm)
- [Prometheus: OpenTelemetry guide (OTLP receiver)](https://prometheus.io/docs/guides/opentelemetry/); [Prometheus feature flags](https://prometheus.io/docs/prometheus/latest/feature_flags/); [prometheus_client multiprocess mode](https://prometheus.github.io/client_python/multiprocess/)
- Langfuse: [self-hosting overview](https://langfuse.com/self-hosting), [docker compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose), [masking](https://langfuse.com/docs/observability/features/masking), [existing OTel setup FAQ](https://langfuse.com/faq/all/existing-otel-setup), [export-stage masking changelog](https://langfuse.com/changelog/2026-06-16-python-sdk-export-stage-masking), [pricing](https://langfuse.com/pricing)

---

**Change log**: 2026-09-27: spec-impact disposition added (A-22); span-attribute prefix and other identifiers renamed for Ticketward (`tw.*`).

**Document Version**: 1.1
**Next Update**: P7 (re-pin versions; validate the redaction allow-list against real spans)
