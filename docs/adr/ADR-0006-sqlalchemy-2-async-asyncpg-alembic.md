---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §0 (reference patterns), §7.1 (layering), §10 (schema, roles, purge, migrations), §12.3
informed: contributors
supersedes: none
amended: 2026-09-27 (spec v1.1 alignment; decision unchanged)
---

# ADR-0006: SQLAlchemy 2.0 async with asyncpg and Alembic

> **Amended in spec v1.1 (2026-09-27): alignment only; the decision is unchanged.**
> * New role **`tw_purger`** (NOLOGIN). It owns the `SECURITY DEFINER` purge functions `tw_purge_ticket()`,
>   `tw_retention_purge()` and `tw_shred_period()`, each with a fixed `search_path` (A-25(f)). `tw_app` only gets
>   EXECUTE on them.
> * New tables: `user_queue_memberships`, `audit_chain_checkpoints`, `data_encryption_keys`, `deletion_ledger`.
>   `audit_log.id` is `bigint GENERATED ALWAYS AS IDENTITY` plus `public_id uuid`, with `PK(id, created_at)` because
>   of partitioning (A-25(b)).
> * Extensions are created by `infra/postgres/init.sql`; Alembic `0001_extensions` is an idempotent guard (A-28).
>   The HNSW index is built `CONCURRENTLY` in a non-transactional step.
> * CI runs migrations up/down/up against a **service-container** pgvector Postgres (testcontainers locally).
> * Known P0 gap until P4: the scaffold connects as the bootstrap superuser (R-24). P4 creates the `tw_*` roles from
>   Docker secrets.

## Context and Problem Statement

The schema in spec §10 is Postgres-heavy:

* UUID PKs, `timestamptz`, PG enums generated from Python enums;
* typed JSONB (`output`, `rules_fired`, `details`), arrays, `inet`, `citext`, pgvector `vector(384)`;
* CHECK constraints (four-eyes with `approval_bypass_reason`, approved-by-not-null);
* partial unique indexes, GIN, trigram and partial HNSW indexes;
* monthly **range-partitioned** `llm_calls` and `audit_log`.

The owner's reference project used raw `CAST(:x AS JSONB)` SQL strings. Spec §0 replaces that with SQLAlchemy 2.0
typed JSONB, and allows raw SQL only in Alembic migrations, parameterized. The stack is async all the way (§14.2). The
layering rule `api → services → … → repositories → db` is enforced by import-linter (§7.1).

Privileges are split:

| Role | Rights |
|---|---|
| `tw_migrator` | DDL; runs in a one-shot `migrate` service |
| `tw_app` | DML; no DDL; no UPDATE/DELETE on `audit_log`, `audit_chain_checkpoints`, `deletion_ledger`, `feedback_events`; EXECUTE on the purge functions |
| `tw_readonly` | dashboards |
| `tw_purger` | NOLOGIN; owns the purge functions |

Which data-access and migration stack meets these typing, safety and async requirements?

## Decision Drivers

* Injection safety by construction: bound parameters only (A05:2025 Injection), with no string-built SQL outside
  migrations.
* Typed mappings that pass `mypy --strict` (§14.2).
* Async support with a fast Postgres driver.
* Expressiveness for Postgres DDL: enums, partial indexes, partitions, identity columns, `SECURITY DEFINER` functions
  and pgvector.
* Mature, reviewable, reversible migrations and least-privilege roles.
* Separation between API schemas (`schemas/`) and persistence models (`db/models/`).

## Considered Options

1. SQLAlchemy 2.0 (async ORM + Core) + asyncpg + Alembic (chosen)
2. SQLModel
3. Raw asyncpg
4. Tortoise ORM (+ Aerich)

## Decision Outcome

Chosen option: "SQLAlchemy 2.0 async + asyncpg + Alembic", because it is the most complete typed Python toolkit for
Postgres. SQL stays parameterized by default, every §10 construct is supported (pgvector through the `pgvector`
package's type), and Alembic's revision model matches the migration rules.

Rules:

* Repositories are the only modules that import `ticketward.db` (import-linter). Services never build queries.
* No `text()` with interpolated strings. `text()` is allowed only in Alembic revisions, with bound parameters.
* Explicit loading strategies. Lazy loading is off on async sessions.
* Hand-written, reviewed DDL for what autogenerate misses: partitions, triggers, CHECKs, grants, identity columns,
  the purge functions (owner `tw_purger`, `SECURITY DEFINER`, fixed `search_path`, minimal body), and HNSW options.
* Every non-destructive revision has a working `downgrade()`. Destructive revisions are marked irreversible.
* Monthly partitions are created ahead of time. Only the retention path drops them, after the audit checkpoint and
  off-host export (ADR-0037).

**Verify at build:** the current SQLAlchemy 2.x and Alembic releases, and that the SQLAlchemy mypy plugin is not
needed (inline typing).

### Consequences

* Good, because SQL injection through the data layer needs a deliberate rule violation, which Semgrep and Bandit
  catch.
* Good, because typed `Mapped[...]` models support strict typing and refactoring.
* Good, because destructive operations are concentrated in three audited, owner-restricted `SECURITY DEFINER`
  functions, while the app role keeps no UPDATE/DELETE on append-only tables.
* Bad, because `SECURITY DEFINER` functions are powerful. A mutable `search_path` or broad bodies would allow
  privilege escalation. Mitigation: fixed `search_path`, a NOLOGIN owner, EXECUTE only for `tw_app`, code review and
  integration tests of the purge scope.
* Bad, because async SQLAlchemy and hand-written partition DDL have sharp edges. Mitigation: one session per request
  or job, and migration tests on real Postgres.
* Neutral, because ORM models stay separate from API schemas. That is intentional (no leaked `message_enc`).

### Confirmation

* `backend-integration` CI job: `alembic upgrade head` → `downgrade` → `upgrade head` on a pgvector 0.8.6 service
  container (§10, §14.5 step 4).
* Security stage: Semgrep "no raw SQL strings" and Bandit B608.
* import-linter: only `ticketward.repositories` imports `ticketward.db`.
* `T-SEC-AUDIT-append-only`: as `tw_app`, UPDATE/DELETE on `audit_log`, `audit_chain_checkpoints`, `deletion_ledger`
  and `feedback_events` fail.
* `T-SEC-DB-roles` (proposed name): the purge functions have a fixed `search_path` and owner `tw_purger`; `tw_app`
  cannot create extensions or call DDL. `T-DELETE-purge` covers the purge scope (ADR-0030/0037).
* Lint stage: `mypy --strict` over `db/` and `repositories/`.
* P4 exit: R-24 closed (no bootstrap superuser in any service).

## Pros and Cons of the Options

### SQLAlchemy 2.0 async + asyncpg + Alembic

* Good, because it is the de-facto standard, with a full Postgres dialect and a pgvector type. asyncpg is a fast
  native driver, and Alembic fits a one-shot migrate container.
* Bad, because of the learning curve, async pitfalls and autogenerate blind spots.

### SQLModel

* Good, because one class serves as both Pydantic model and table.
* Bad, because it couples API contracts to persistence. Reusing table models as responses can leak sensitive columns,
  and it lags SQLAlchemy features.

### Raw asyncpg

* Good, because it is the fastest option with full control.
* Bad, because every query is hand-written SQL (conflicts with the "no raw SQL" rule), with no typed mappings and a
  separate migration tool anyway.

### Tortoise ORM (+ Aerich)

* Good, because it is async-native with a Django-like API.
* Bad, because its ecosystem is smaller, its typing weaker, its pgvector and partitioning support less mature, and
  Aerich is less proven.

## More Information

* Spec (private): §0 (reference patterns), §7.1, §10 (conventions, tables, roles, purge functions, retention,
  migrations), §12.3, §14.2, §14.3, §14.5, §21 R-24. Change record A-25 (b)(f), A-28, A-29 (h).
* Research: [hybrid-retrieval](../research/hybrid-retrieval.md) (pgvector DDL);
  [cryptography-key-management](../research/cryptography-key-management.md) (DEK table, purge functions). No
  dedicated ORM topic.
* Related ADRs: ADR-0004, ADR-0005, ADR-0030, ADR-0037.
* Revisit when: a PostgreSQL major upgrade needs dialect changes, or partition management moves to an extension (for
  example pg_partman).
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 updated for spec v1.1 (`tw_purger` and purge functions, new
  tables, CI service containers; decision unchanged).
