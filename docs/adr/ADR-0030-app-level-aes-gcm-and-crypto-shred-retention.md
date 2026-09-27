---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §4 (PR-008, PR-010), §6.1, §7.2, §10 (encryption, tickets, retention, deletion), §12.2, §12.5, §12.6, §15; research cryptography-key-management, pii-masking-presidio
informed: admin persona (deletion requests); operators (key rotation, restore)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0030: App-level AES-256-GCM for raw ticket text, with retention and purge

> **Amended in spec v1.1 (2026-09-27; change record A-17, A-25(a)(f), W-m10, lead confirmation 11).**
> * **Card numbers are reduced to their last 4 digits before encryption** (PCI DSS Req. 3; verify before any real
>   deployment).
> * **Step 0 stores only the encrypted raw envelope** (subject + message + thread) with the current period DEK. The
>   masked copies (`subject_masked`, `message_masked`, `body_masked`) are written in step 1. `tickets.subject` is
>   stored masked; the raw subject lives in the envelope.
> * **The PII map** is its own envelope (`pii_map_enc` + `pii_map_key_id`, AAD = ticket id ‖ `pii_map` ‖ key id). The
>   v1.0 schema gap this ADR flagged is resolved.
> * **Key management and crypto-shred move to ADR-0037:** per-period (monthly) DEKs wrapped by a KEK, a deletion
>   ledger re-applied after restores, and backups holding only wrapped keys. This resolves the v1.0 open issue
>   ("nulling columns is not crypto-shred") and the restore caveat.
> * **The purge scope covers every text column** (drafts, citation quotes, feedback text, handoff content, triage
>   output, retrieval query), via the `SECURITY DEFINER` function `tw_purge_ticket()` owned by `tw_purger`. It writes
>   the tombstone `ticket.purged` and a `deletion_ledger` row. PR-010 closes in P9.

## Context and Problem Statement

Raw ticket content may contain personal data. It is synthetic in the demo, but the controls are designed as if it
were real. Two copies exist (spec §10):

* an **encrypted raw envelope**: `tickets.message_enc` (subject + message), `ticket_messages.body_enc`,
  `customer_email_enc`, and the PII map `pii_map_enc`;
* **masked copies**: `subject_masked`, `message_masked`, `body_masked`, used by models, search (trigram), eval and the
  default UI.

Retention and deletion requirements (§10):
* raw text and the map are kept 90 days;
* `llm_calls` 180 days;
* audit and security logs 1 year;
* idempotency keys 24 h;
* revoked sessions 30 days;
* an admin deletion request hard-purges every in-scope text column and leaves a tombstone.

How should raw text be protected at rest, and how are retention and deletion enforced?

## Decision Drivers

* Plaintext never reaches the database server, its logs, dumps or the read-only role.
* Key separation: keys come from the secret store, never the database. A key id per row enables rotation.
* Integrity: ciphertext cannot be modified or swapped between rows or columns undetected (AEAD with AAD).
* Minimisation before encryption (PAN last-4).
* Enforceable, auditable deletion: retention, per-ticket purge and period crypto-shred (ADR-0037).
* Vetted libraries only (ASVS V11).

## Considered Options

1. App-level AES-256-GCM (Python `cryptography` AEAD) with key ids per row, plus a retention job, purge functions and
   period DEKs (ADR-0037) (chosen)
2. pgcrypto only (database-side encryption)
3. Disk or volume encryption only

## Decision Outcome

Chosen option: "app-level AES-256-GCM with key ids per row", because it is the only option where the database, its
dumps and its roles never see plaintext or keys, and where each ciphertext is bound to its row and purpose.

Design:

* **Primitive:** AES-256-GCM via `cryptography`'s AEAD, with a 96-bit random nonce per encryption, never reused under
  a key. Volume is far below the random-nonce guidance (about 2³² encryptions per key, NIST SP 800-38D).
* **AAD:** binds ticket id, purpose (column) and key id. For the map this is `ticket_id ‖ pii_map ‖ key_id` (§10). A
  ciphertext copied to another row or column fails authentication.
* **Stored format:** version ‖ key id ‖ nonce ‖ ciphertext ‖ tag in `bytea`, with the row's `enc_key_id`, for example
  `dek-2026-09`.
* **Keys:** per-period DEKs wrapped by a KEK from the secret store (ADR-0037). The DEK for the current month encrypts
  new rows.
* **Minimisation:** Luhn-valid PANs are reduced to the last 4 digits in step 0, before encryption (A-17).
* **Retention (nightly `retention_job`):**
  * `tw_retention_purge()` nulls the raw columns and the map at 90 days and sets `raw_purged_at`;
  * `tw_shred_period()` destroys a month's DEK once that month's newest row is 90 days old (ADR-0037);
  * `llm_calls` and `audit_log` partitions are dropped after the off-host export and checkpoint;
  * expired idempotency keys and revoked sessions are purged;
  * `retention.purge` is audited.
* **Deletion request:** `DELETE /api/v1/tickets/{id}` (admin, `DEMO_LOCKED` in demo) calls `tw_purge_ticket()`, which
  purges:
  * `message_enc`, `subject_masked`, `message_masked`, `customer_email_enc`;
  * thread `body_enc` and `body_masked`;
  * `pii_map_enc`;
  * draft `body_markdown`, `sentences`, `final_text`, `template_reply` and citation quotes;
  * feedback `edited_text`, `comment`, `corrected_value`;
  * handoff content;
  * triage `raw_output_masked` and `output`;
  * `retrieval_runs.query_masked`.

  It writes the tombstone `ticket.purged` and a `deletion_ledger` row. A per-ticket purge is a hard purge (other
  tickets share the period DEK). The period shred is the retention path.

### Consequences

* Good, because SQL injection, a leaked `tw_readonly` credential or a stolen dump yields ciphertext and masked text
  only, and card data is minimised even inside the ciphertext.
* Good, because rows are bound by AAD, and key ids allow rotation without downtime.
* Good, because deletion is complete (every text column), audited, tombstoned and ledgered, and restores re-apply it
  (ADR-0037).
* Bad, because raw text cannot be searched in the database (by design: search uses the masked copy).
* Bad, because losing the KEK means losing all raw text still within retention. The KEK backup and rotation procedure
  lives in `rotate-secrets.md` (ADR-0037).
* Neutral, because disk encryption on the host is still recommended as an additional layer.

### Confirmation

* `T-SEC-CRYPTO-*` (`core/crypto.py`, under the ≥ 95% branch coverage of `core/security`):
  * round-trip;
  * a flipped bit fails authentication;
  * an AAD mismatch (row or purpose swap) fails;
  * no nonce repeats across 10⁵ encryptions;
  * the key id is recorded;
  * rotation keeps old rows readable until re-wrap.
* `T-SEC-DB-no-plaintext`: a canary ticket leaves no plaintext (or full PAN) in `pg_dump`; the PAN appears as last-4
  only.
* `T-RETENTION-shred`: past the cutoff, the raw columns and map are nulled, the masked copy is kept, and
  `retention.purge` is written. `T-SEC-CRYPTO-shred` (ADR-0037) covers DEK destruction.
* `T-DELETE-purge`: every in-scope column is purged, the `ticket.purged` tombstone and ledger row are written, a
  non-admin gets 403, and demo mode gives `DEMO_LOCKED`.
* Semgrep bans non-AEAD modes, constant nonces, and `random`/`uuid4` for secrets (§12.8).

## Pros and Cons of the Options

### App-level AES-256-GCM (+ retention, purge, period DEKs)

* Good, because keys and plaintext never reach the database, rows are bound by AAD, key ids allow rotation, and it
  uses vetted libraries.
* Bad, because key management is ours, and raw text cannot be queried in the database.

### pgcrypto only

* Good, because encryption is expressed in SQL.
* Bad, because keys travel in SQL statements (logs, `pg_stat_statements`), the database host sees keys and
  plaintext, and there is less control over AEAD and AAD.

### Disk or volume encryption only

* Good, because it is transparent and protects stolen disks and snapshots.
* Bad, because it does nothing against SQL-level access or logical dumps, and gives no per-period or per-ticket
  deletion guarantees. It is recommended **in addition**.

## More Information

* Spec (private): §6.1, §7.2 (steps 0–1), §10 (encryption convention, `tickets`, `ticket_messages`,
  `data_encryption_keys`, `deletion_ledger`, roles, retention, deletion request), §11 (`DELETE /tickets/{id}`,
  reveal), §12.2, §12.5 (map, PAN), §12.6 (key inventory), §15 (backups, restore). Change record A-17, A-25 (a)(f),
  W-m10.
* Brief (private): §10. PR-008, PR-010.
* Research: [cryptography-key-management](../research/cryptography-key-management.md),
  [pii-masking-presidio](../research/pii-masking-presidio.md).
* Related ADRs: ADR-0006 (`tw_purger`), ADR-0019, ADR-0027, ADR-0037 (key hierarchy, shred, ledger).
* Security docs: [audit events](../security/audit-events.md) (`retention.purge`, `ticket.purged`),
  [threat model](../security/threat-model.md).
* Revisit when: a KMS/HSM becomes available, or real authorised data is processed.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (PAN last-4, step-0 envelope, PII-map
  envelope, full purge scope, key management moved to ADR-0037).
