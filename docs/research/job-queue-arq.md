# Job Queue: arq on Redis - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-27
**Last Updated**: 2026-09-27
**Status**: Open (stub; research not started)
**Owner phase**: P4 (arq worker, msgpack). Trace propagation is P7; Redis ACL/TLS is P9.
**Category**: Backend / Async jobs
**Linked ADR(s)**: ADR-0022 (arq + Redis; msgpack serializer; manual trace propagation; Redis ACL); related ADR-0024 (observability)
**Spec sections**: §7.1, §7.2, §15, §16 P4/P7/P9, §23

---

## EXECUTIVE SUMMARY

- This is a **stub**. It was created for the spec v1.1 topic list (A-26), and no research has been run yet.
- It collects the required questions and points to findings that other research notes have already recorded. Nothing here is new, and nothing has been re-verified.
- Run the full protocol before the P4 worker work. See [README.md](README.md) for the process and template.

---

## QUESTIONS (from spec §23)

1. Which arq version, and what is its maintenance status?
2. How is the msgpack serializer configured, and what is the primitive-only job contract?
3. How do we handle retries, idempotent job ids and dead-lettering?
4. How does manual OTel propagation work?
5. What are the Redis ACL and TLS options?
6. What are the alternatives if arq stalls?

---

## KNOWN SO FAR (recorded in other research notes; not re-verified)

- **Version and API (Q1–Q3).** [observability-otel.md](observability-otel.md) F1/F3 recorded (accessed 2026-09-26):
  - arq 0.28.0 is the latest on PyPI (2026-04-16).
  - `enqueue_job(function, *args, _job_id, _queue_name, _defer_until, _defer_by, _expires, _job_try, **kwargs)` returns `Job`, or `None` when a job with that id already exists.
  - The worker `ctx` holds `job_id`, `job_try`, `enqueue_time` and `redis`.
  - `WorkerSettings` options include `on_startup`, `on_shutdown`, `on_job_start`, `on_job_end`, `after_job_end`, `max_jobs`, `job_timeout`, `max_tries`, `keep_result`, `job_serializer` and `job_deserializer`.
  - The docs warn that jobs may run more than once, so tasks must be idempotent.
- **Serializer (Q2).** The same note records that arq's **default serializer is `pickle`** (`arq/jobs.py`). The arq docs show a msgpack example for both `create_pool(...)` and `WorkerSettings`. Its D3 design requires msgpack on both sides, with job arguments and return values restricted to msgpack primitives.
- **Why msgpack (Q2).** [owasp-asvs-l2.md](owasp-asvs-l2.md) ties the change to ASVS v5.0.0-1.5.2 (L2, safe deserialisation; its SI-S8, applied in v1.1).
- **Trace propagation (Q4).** [observability-otel.md](observability-otel.md) records:
  - opentelemetry-python-contrib has **no arq instrumentation** (F2).
  - D3 designs manual W3C propagation: `propagate.inject` into a job kwarg at enqueue, and a `@traced_job` decorator that extracts it and opens a CONSUMER span.
- **Redis ACL and TLS (Q5).** [owasp-asvs-l2.md](owasp-asvs-l2.md) D2/D4 recommend Redis TLS (TLS port + ACL), or a documented intra-host deviation, and individual service accounts (Redis ACL users, 13.2.1).
- **Operations.** [public-demo-deployment.md](public-demo-deployment.md) D6/D7 record queue-depth backpressure (429 above 20 queued jobs), worker `max_jobs=2`, draining the worker before the nightly reset, and that `FLUSHDB` clears queued jobs.
- **Not yet researched:** maintenance status and release cadence, retry semantics and dead-lettering, Redis TLS configuration with arq, and alternatives.

---

## FINDINGS

None yet. Research not started.

## DECISION / RECOMMENDATION

None yet. ADR-0022 currently fixes arq + Redis with msgpack and manual trace propagation.

## SPEC IMPACT

None yet.

## IMPLEMENTATION CHECKLIST

- [ ] Run ERPROT research for Q1–Q6 before P4, from primary sources (arq docs and source, Redis docs), with access dates.
- [ ] Record the pinned version, serializer settings, retry and idempotency policy, and the Redis ACL/TLS setup, and update this file's status.

## OPEN RISKS / TO VERIFY

- The arq facts above were recorded on 2026-09-26 for observability purposes. Re-verify the version and API at P4.

## LINKED ADR

- **ADR-0022**: record the pinned arq version, the serializer contract, the retry/idempotency policy and the Redis ACL/TLS choice.

## SOURCES

Pointers only. Primary sources, with access dates, are listed in the linked notes: [observability-otel.md](observability-otel.md), [owasp-asvs-l2.md](owasp-asvs-l2.md), [public-demo-deployment.md](public-demo-deployment.md).

---

**Document Version**: 0.1 (stub)
**Next Update**: Before P4 worker implementation
