---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §10 (encryption convention, data_encryption_keys, deletion_ledger, roles, retention, deletion request), §12.6, §15 (backup/restore), §16 P4/P9, §24.4–§24.5; research cryptography-key-management
informed: operators (KEK custody, restore drill); admin persona (deletion requests)
supersedes: none
amended: none
---

# ADR-0037: Crypto-shred with per-period DEKs, a KEK, and a deletion ledger

## Context and Problem Statement

Raw ticket text and the PII map are encrypted at the application level (ADR-0030). They must become unrecoverable:
* **90 days** after ingestion (retention);
* **on request** (PR-010).

v1.0 nulled the columns. The spec review showed that this is not crypto-shred:
* the plaintext-equivalent ciphertext stays in nightly backups (up to 6 weeks) together with a key that still works;
* restoring a backup would **resurrect** expired or deleted content;
* a single static key cannot be destroyed without destroying all data.

Change record A-25(a) adopted per-period keys and a deletion ledger.

How are data keys organised, destroyed and protected so that retention and deletion also hold for backups and
restores?

## Decision Drivers

* Retention must hold for backups within a bounded window, not only for the live database.
* A restore must never resurrect purged or expired content (the ledger re-applies before serving).
* Keys are never stored in usable form in the database or its dumps.
* Few keys, simple operations (single host, one operator), rotation without downtime.
* Auditable evidence of every destruction (ASVS 11.1.1 key lifecycle; 14.2.4 retention).

## Considered Options

1. Per-period (monthly) DEKs wrapped by a KEK from the secret store, plus an append-only deletion ledger re-applied
   after restores; backups hold only wrapped DEKs (chosen)
2. One static key
3. Per-row keys
4. Deleting backups

## Decision Outcome

Chosen option: per-period DEKs + KEK + deletion ledger (spec §10, §12.6, §15), because destroying one small key per
month makes that month's ciphertext unrecoverable everywhere it was copied. The ledger closes the restore gap for
both period shreds and per-ticket purges.

**Key hierarchy:**
* **KEK:**
  * 256-bit, in the secret store (SOPS + age → Docker secret under `/run/secrets`, mode 0400), identified by
    `kek_id`;
  * never in the database, images, logs or the DB dump;
  * the previous KEK is kept until every backup that needs it has aged out (≤ 6 weeks), then destroyed.
* **DEKs:**
  * one per calendar month (`key_id` = `dek-YYYY-MM`), 256-bit from the OS CSPRNG;
  * created at first use in a period (audited `crypto.dek_created`);
  * stored only **wrapped by the KEK** in `data_encryption_keys (key_id, wrapped_dek, kek_id, created_at,
    destroyed_at)`;
  * unwrapped DEKs live only in process memory (bounded cache), never in logs, traces or errors.
* **Wrap mechanism:** an AEAD wrap with the `key_id` bound as associated data, via `cryptography`. The exact choice
  (AES-256-GCM wrap vs AES-KWP, RFC 5649) is confirmed by the `cryptography-key-management` research before P4 and
  recorded in `docs/security/crypto-inventory.md`.

**Row encryption:** AES-256-GCM with the current period DEK (ADR-0030). Every row stores `enc_key_id`. The AAD binds
ticket id, purpose and key id.

**Destruction paths (all through `SECURITY DEFINER` functions owned by `tw_purger`, fixed `search_path`; ADR-0006):**

| Path | Function | Effect | Evidence |
|---|---|---|---|
| Per-row retention (90 days) | `tw_retention_purge()` | nulls the raw columns and `pii_map_enc`, sets `raw_purged_at` | `retention.purge` audit |
| Period crypto-shred | `tw_shred_period()` | once the newest row of month M is 90 days old: `wrapped_dek = NULL`, `destroyed_at = now()` | `deletion_ledger` (`period_shred`, `key_id`) + audit |
| Deletion request | `tw_purge_ticket(ticket_id, request_id)` | hard purge of every in-scope text column (ADR-0030) | `deletion_ledger` (`ticket_purge`) + `ticket.purged` tombstone |

**Deletion ledger:**
* `deletion_ledger (id, action, target_type, target_id, key_id, requested_by, request_id, audit_public_id,
  executed_at)`;
* append-only for `tw_app`;
* **every entry is also written to the off-host log sink**;
* preserved across demo resets (ADR-0035).

**Restore:** `scripts/restore.sh` restores into a scratch database, **re-applies the off-host ledger** (re-runs every
purge and shred newer than the backup) **before** the restored database serves traffic, runs the smoke test, and
records the replay (`restore.ledger_replayed`). Monthly drill; P9 exit criterion (RPO 24 h / RTO 1 h).

**Backups:**
* restic, client-side encrypted, 14 daily + 4 weekly (≤ 6 weeks);
* they hold **only wrapped DEKs**;
* the age key and restic password are kept off the VM.

The bound is: content destroyed at time t can be recovered only from a backup taken before t, only by someone holding
that backup, its restic password **and** the KEK, and only until that backup expires (≤ 6 weeks).

### Consequences

* Good, because after a period shred, that month's raw text is unrecoverable from the database, WAL, dumps and (after
  ≤ 6 weeks) every backup, even if a column was missed.
* Good, because restores cannot resurrect content (ledger replay before serving). Per-ticket purges survive restores.
* Good, because there are only 12 DEKs per year, and KEK rotation re-wraps a dozen rows without touching ciphertext.
* Bad, because losing the KEK loses all raw text still in retention. The KEK has an off-VM copy in the owner's
  password manager, and the rotation runbook covers re-wrap (`rotate-secrets.md`).
* Bad, because per-ticket deletion is a hard purge, not a crypto-shred: other tickets share the DEK. The ticket's
  ciphertext stays in backups until they expire. The ledger re-applies the purge after any restore.
* Bad, because the guarantees depend on off-VM custody (age key, restic password) and on bucket settings that really
  delete expired objects (object versioning and lifecycle rules; verify at P9).
* Neutral, because masked copies are kept for evaluation. They are unencrypted by design and contain no raw PII
  (ADR-0019).

### Confirmation

* `T-SEC-CRYPTO-shred`:
  * after `tw_shred_period('2026-06')`, rows with `enc_key_id = dek-2026-06` fail to decrypt (key destroyed);
  * `wrapped_dek IS NULL` and `destroyed_at` is set;
  * the ledger row and audit event are written;
  * other periods still decrypt.
* `T-RESTORE-ledger`:
  * restore a pre-shred / pre-purge dump into a scratch database;
  * `restore.sh` re-applies the ledger;
  * the purged ticket's columns are NULL and the shredded DEK is NULL **before** the API is started against it;
  * `restore.ledger_replayed` is recorded.
* `T-SEC-DB-no-plaintext` (extended): a canary ticket's plaintext, any unwrapped DEK and the KEK never appear in
  `pg_dump` output, logs or traces.
* KEK rotation test: new KEK → re-wrap → every row still decrypts; the old KEK is removed after the backup window.
* Startup validation: prod refuses to boot without a KEK, or if the current-period DEK cannot be unwrapped.
* `tw_app` has no UPDATE/DELETE on `deletion_ledger`; only the purge functions change `data_encryption_keys`
  (privilege test).
* The monthly restore drill result is recorded in `system-status.md`.

## Pros and Cons of the Options

### Per-period DEKs + KEK + deletion ledger (chosen)

* Good, because it gives time-bounded unrecoverability everywhere, restore-safe deletion, few keys, and cheap
  rotation.
* Bad, because of KEK custody, a hard purge (not crypto-shred) for single tickets, and the dependence on backup
  expiry.

### One static key

* Good, because it is simplest.
* Bad, because it cannot be destroyed without losing everything. Nulling columns is not shred, and backups plus the
  still-valid key resurrect content.

### Per-row keys

* Good, because it allows true per-ticket crypto-shred.
* Bad, because a key table as large as the data, stored in the same database and backups, gains nothing unless the
  keys live elsewhere. It adds complexity, and a ledger is still needed for restores.

### Deleting backups

* Good, because it removes old copies directly.
* Bad, because it destroys disaster-recovery capability (RPO/RTO), and restic snapshots of a DB dump cannot be edited
  selectively. Deleting whole snapshots is all-or-nothing.

## More Information

* Spec (private): §10 (encryption convention, `data_encryption_keys`, `deletion_ledger`, `tw_purger` functions,
  retention, deletion request), §12.6 (KEK in the secret store, key inventory), §15 (backups hold only wrapped DEKs;
  restore re-applies the ledger), §16 P4 (period DEKs in `core/crypto.py`) and P9 (restore drill), §24.4 (ledger
  preserved across resets), §24.5 (demo backups). Change record A-25(a), A-25(f).
* Research: [cryptography-key-management](../research/cryptography-key-management.md) (a stub at the time of
  writing; the research must run before P4).
* Related ADRs: ADR-0006 (`tw_purger`, roles), ADR-0030 (row encryption, purge scope), ADR-0035 (reset preserves the
  ledger), ADR-0026 (restic, SOPS + age).
* Security docs: [audit events](../security/audit-events.md) (`crypto.*`, `restore.ledger_replayed`,
  `retention.purge`, `ticket.purged`), [threat model](../security/threat-model.md) (restore resurrection abuse case).
* Open item (reported to the lead): §15/§10 say the KEK is never in a backup, while §24.5 backs up the
  SOPS/age-encrypted secrets bundle, which holds the KEK in age-encrypted form. Either exclude the KEK from the
  backed-up bundle, or restate the guarantee as "only age-encrypted, with the age key off the VM".
* Revisit when: a KMS/HSM is available (move the KEK), the retention period changes (the DEK period may shorten), or
  real authorised data is processed.
* Status history: 2026-09-27 Accepted (new in spec v1.1, change record A-25(a)). The wrap mechanism is confirmed
  before P4 by the named research.
