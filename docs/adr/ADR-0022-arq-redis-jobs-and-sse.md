---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §7.1, §7.2, §7.7, §10 (processing_jobs), §11 (SSE), §12.6, §12.11, §15, §24.3; research job-queue-arq, observability-otel
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0022: arq on Redis for pipeline jobs; SSE to the UI

> **Amended in spec v1.1 (2026-09-27; change record A-21, A-22, A-25(c), A-23).**
> * **msgpack serializer on both producer and worker** (no pickle; ASVS 1.5.2). Job arguments and results are
>   msgpack primitives only (ids, the trace-context carrier, None). This resolves the v1.0 pickle-by-default risk this
>   ADR flagged.
> * **Redis ACL user + password.** The config is rendered into a tmpfs at container start from a Docker secret.
>   Internal network only, no published port.
> * **Manual trace propagation:** the W3C `traceparent` is injected into a job kwarg at enqueue and extracted by a
>   `@traced_job` decorator, since contrib has no arq instrumentation.
> * **SSE heartbeat every 20 s** (≤ 30 s, below Cloudflare's 125 s idle timeout). The `sid` revocation is re-checked on
>   each heartbeat, and the stream closes when the session is revoked.
> * **Queue-depth backpressure:** 429 with `Retry-After`, and in the demo when depth > 20.
> * The research topic this ADR lacked now exists: **`job-queue-arq`** (A-26).
> * Redis is also the session-revocation store (ADR-0020), which makes it a hard auth dependency (R-20).

## Context and Problem Statement

A ticket's pipeline takes seconds to tens of seconds on CPU (45 s total budget, §7.7):
1. sanitize and PII-mask;
2. triage ∥ retrieval;
3. policy;
4. draft;
5. verify and guards;
6. persist.

`POST /tickets` therefore returns **202** with a `job_id`, and the work runs asynchronously (§7.2). The UI subscribes
to `GET /tickets/{id}/events` (SSE: `ticket.processing`, `ticket.ready`, `ticket.failed`), at most one concurrent
stream per ticket per user (§11). The worker caps concurrency at `max_jobs=2` so the CPU SLM is not oversubscribed.

Scheduled jobs are also needed: the retention and purge jobs, the KB staleness scan, the idempotency purge, the
email-feed poller and the demo reset. The stack is async Python throughout.

Redis is now security-relevant twice over. It carries jobs (which must never become code), and it holds the revoked-
`sid` set and the rate-limit counters (ADR-0020).

How should background jobs run, and how should the UI learn about results, safely?

## Decision Drivers

* An asyncio-native worker sharing the backend's providers and ports.
* Durable jobs with retries, dead-lettering and bounded concurrency.
* **No code execution from queue contents**: primitive-only, msgpack.
* An authenticated, internal-only Redis.
* A simple, secure server-to-browser push through Caddy, and Cloudflare in Phase 2.
* End-to-end tracing across the enqueue/consume boundary.

## Considered Options

1. arq on Redis (msgpack, ACL) for jobs and cron; SSE for UI notifications (chosen)
2. Celery
3. RQ
4. FastAPI `BackgroundTasks`
5. WebSockets instead of SSE

## Decision Outcome

Chosen option: "arq on Redis with msgpack and an ACL, plus SSE", because arq is a small asyncio-native queue with
retries, results and cron. Redis is needed anyway for rate limits and revocation. SSE is the simplest one-way push
that works through the proxy.

Rules:

* **Serialization:** `job_serializer`/`job_deserializer` = msgpack on the API's `ArqRedis` pool and in the worker
  settings. The job contract is primitives only (`ticket_id`, `job_id`, `traceparent`). Semgrep bans `pickle` in
  `backend/` (§12.8).
* **Redis:** ACL user + password from a Docker secret, config rendered to tmpfs, internal network only. Dangerous
  commands are denied for the app user (proposed detail; research `job-queue-arq`).
* **Idempotency:** jobs are at-least-once. `processing_jobs` rows key them, reprocessing creates a new `triage_run`,
  attempts are bounded, and exhausted jobs are marked `dead`.
* **SSE:**
  * authenticated by the access cookie (same-origin; Fetch Metadata applies);
  * authorised by object scoping (out of scope → 404);
  * one stream per ticket per user;
  * heartbeat every 20 s, with the `sid` revocation re-checked on each heartbeat;
  * payloads carry **ids and status only**, and the UI re-fetches through the authorised API.

  Caddy flushes SSE immediately (§24.2). Background SSE reconnects do not extend a session.
* **Backpressure:** queue depth above a threshold gives 429 `RATE_LIMITED` with `Retry-After` (demo: > 20). There is
  an alert when depth > 20 for 10 min.
* **Tracing:** `traceparent` in a job kwarg, and `@traced_job` producer/consumer spans (ADR-0024).

**Verify at build (research `job-queue-arq`):** the arq version and maintenance status, the msgpack configuration,
retries and dead-lettering, and the Redis ACL command set.

### Consequences

* Good, because API latency stays flat, CPU work is isolated in the worker, and concurrency is capped where the SLM
  runs.
* Good, because a write-capable attacker on Redis cannot get code execution through the queue (msgpack primitives),
  and needs the ACL credentials to write at all.
* Good, because revoked sessions lose their streams within one heartbeat.
* Bad, because Redis is a hard dependency of both jobs and authentication (R-20): an outage stops logins and
  mutations (fail closed). This is accepted for the demo, covered by `redis-outage.md` and healthchecks.
* Bad, because arq's ecosystem is smaller than Celery's. Its maintenance status is tracked in the research topic, with
  a documented alternative if arq stalls.
* Neutral, because SSE is one-way, and actions still go through REST with CSRF (ADR-0020).

### Confirmation

* Integration test (Redis service container): job lifecycle `queued → running → succeeded|failed|dead`, bounded
  retries, idempotent reprocessing.
* `T-SEC-REDIS-serializer`: worker settings and the API pool use msgpack. A pickled payload is rejected without being
  deserialised. The job-argument schema is primitives only.
* `T-SEC-REDIS-auth`: unauthenticated or wrong-user connections fail. The app user cannot run denied commands
  (proposed detail).
* `T-SEC-SSE-limits` and `T-SEC-SSE-authz`:
  * a second stream for the same ticket and user gets 429;
  * unauthenticated gets 401;
  * out of scope gets 404;
  * a heartbeat arrives ≤ 30 s;
  * a revoked `sid` closes the stream;
  * payloads carry no ticket content.
* A trace-propagation test: the job span links to the request span.
* The `tw_jobs_queue_depth` alert rule is present, and checked with `promtool test rules` (proposed).

## Pros and Cons of the Options

### arq + Redis (msgpack, ACL) + SSE

* Good, because it is asyncio-native and lightweight, with retries, results and cron, and it reuses Redis.
* Bad, because its community is smaller, and Redis becomes a critical, security-relevant dependency.

### Celery

* Good, because it is mature and feature-rich, with good monitoring.
* Bad, because it is sync-first, with a heavier config surface. It is overkill for one queue with `max_jobs=2`.

### RQ

* Good, because it is very simple.
* Bad, because it is synchronous with a fork-per-job model, a mismatch with the async providers.

### FastAPI `BackgroundTasks`

* Good, because it has zero dependencies.
* Bad, because tasks run in the API process after the response. They are lost on restart, with no retries and no
  cross-process cap. That is unacceptable for 15–45 s CPU pipelines.

### WebSockets

* Good, because they are bidirectional.
* Bad, because only server→client status is needed. WebSockets add an upgrade path, cross-site WebSocket hijacking
  checks and custom auth handling.

## More Information

* Spec (private): §6.1 (email feed worker), §7.1, §7.2, §7.7 (heartbeat), §10 (`processing_jobs`), §11 (202, SSE,
  heartbeat and revocation), §12.6 (Redis secret), §12.11 (Redis ACL, msgpack), §15 (manual propagation, queue-depth
  alert, `redis-outage.md`), §24.3 (queue-depth 429), §24.4 (reset flushes Redis). Change record A-21, A-22, A-25 (c),
  A-23, A-26.
* Research: [job-queue-arq](../research/job-queue-arq.md),
  [observability-otel](../research/observability-otel.md).
* Related ADRs: ADR-0020 (revocation set), ADR-0021 (scoping), ADR-0024 (tracing), ADR-0026 (networks), ADR-0035
  (demo reset).
* Security docs: [threat model](../security/threat-model.md) AC-11, AC-22, AC-29.
* Revisit when: more than one worker host is needed, arq maintenance stalls, or bidirectional real-time features are
  added.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (msgpack, Redis ACL, manual trace
  propagation, SSE heartbeat and revocation re-check, backpressure).
