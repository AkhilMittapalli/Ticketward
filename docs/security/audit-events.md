# Ticketward: Audit Events Catalogue

| Field | Value |
|---|---|
| Document | `docs/security/audit-events.md` (the audit coverage list referenced by spec §12.10) |
| Version / date | 0.2 · 2026-09-27 (aligned to spec v1.1) |
| Owner | Akhil Mittapalli |
| Status | Draft. No events are implemented yet. Implementation phases: P4 (auth, sessions, PII, tickets, users, DEKs), P5 (KB), P6 (drafts, KB lint), P7 (escalations, rules, models, frontier, feedback export, admin users/sessions), P9 (retention, shred, integrity, restore, egress), P11 (demo mode and reset) |
| Related | [Threat model](threat-model.md) (C-AUD-01..03) · [ASVS checklist](asvs-l2-checklist.md) (V16) · spec §10 (`audit_log`, `audit_chain_checkpoints`, `deletion_ledger`), §11, §12.2 (Repudiation), §12.3 A09, §12.10, §15, §24.4 |

This catalogue is the single source of truth for **what is audited, by whom, with which fields, for how long, and
who may read it**. A privileged or accountability-relevant route or job missing from this catalogue fails the coverage
test (§10, `T-AUDIT-coverage`). Action names already fixed by the spec are used verbatim: `kb.approve`,
`kb.approve_bypass`, `kb.approve_with_lint_override`, `model.activate`, `pii.reveal`, `rules.activate`,
`auth.login_failed`, `ticket.purged`, `demo.reset_completed`, `feedback.export`, `retention.purge`.

---

## 1. Sinks

| Sink | Contents | Integrity | Retention | Read access |
|---|---|---|---|---|
| **`audit_log` table** (PostgreSQL, monthly partitions) | The accountability events in §6 | Append-only for `tw_app` (INSERT/SELECT only) + SHA-256 hash chain anchored by `audit_chain_checkpoints` (§3) | **1 year** (A-25(m)); a partition is dropped only after its off-host export and a checkpoint row | `admin`, and `ops_lead` (read), via `GET /api/v1/admin/audit-log`; entries identified by `public_id` |
| **`audit_chain_checkpoints`** | Chain anchors: `period`, `first_audit_id`, `last_audit_id`, `last_hash`, `row_count`, `exported_uri`, `reason` ∈ {`partition_drop`, `demo_reset`, `monthly`} | Append-only for `tw_app` | Kept with the audit history (not specified; proposed: as long as any exported partition is kept) | `admin` |
| **`deletion_ledger`** | `ticket_purge` and `period_shred` entries (`target_type`, `target_id`, `key_id`, `requested_by`, `request_id`, `audit_public_id`) | Append-only for `tw_app`; every entry also written to the off-host sink; re-applied by `scripts/restore.sh` after any restore | **Not specified** (AE-11; proposed: indefinitely, since entries hold no content) | `admin` |
| **Structured security log** (structlog JSON → stdout → Docker `local` driver → Collector → off-host sink) | High-volume security signals (§7), incl. egress-proxy denials | Not tamper-evident; shipped off-host (A-21/SI-S7) | **1 year** (A-25(m)) | Operators with host access; Grafana (internal, SSH tunnel) |
| **Off-host sink** (service chosen at P9; minimum: nightly encrypted restic copy) | Audit partitions, checkpoints, the deletion ledger, security logs | Logically separate from the app host (ASVS 16.4.3; EX-05 if not in place by P9) | 1 year | Owner |
| Prometheus metrics (internal ports 9464/9465) | Counters behind alerts (§8) | — | Prometheus retention (not specified; its default is 15 days unless configured) | Grafana users |
| Domain tables | `policy_decisions` (`rules_fired`, `deciding_rule_id`), `processing_jobs`, `llm_calls`, `triage_runs`, `feedback_events` (append-only), `auth_sessions` | Per table | Per spec §10 (`llm_calls` 180 days; revoked sessions 30 days) | Per RBAC |

Domain tables are the system of record for high-volume activity: every triage run, policy decision, model call and
feedback event. The audit log records **human or privileged actions and security-relevant system actions**, not every
pipeline step.

**Not an application audit event:** research publishing (`scripts/sync_research.py`, ADR-0038) is a repository
operation. Its evidence is the git history plus the `research-sync` CI log.

---

## 2. Record format

Columns (spec §10):
* `id` **bigint GENERATED ALWAYS AS IDENTITY** and `public_id` uuid (`gen_random_uuid()`), the id used in APIs,
  exports and the deletion ledger;
* `org_id`, `actor_user_id` (nullable), `actor_type` (`user` | `system` | `policy` | `service`);
* `action`, `target_type`, `target_id`, `request_id`, `ip` (`inet`), `details` (`jsonb`, redacted);
* `prev_hash`, `hash` (`bytea`), `created_at` (`timestamptz`).

Keys and indexes: PK(`id`, `created_at`) (the partition key must be in the PK), uq(`public_id`, `created_at`),
idx(`action`, `created_at`), idx(`target_type`, `target_id`).

Conventions:

* **`action`** is `<domain>.<verb>` in lower snake case, stable once shipped. Renaming means adding a new action and
  updating dashboards; old rows keep the old name.
* **`target_type` / `target_id`**: `target_type` is the singular aggregate name (`ticket`, `draft`, `escalation`,
  `handoff_brief`, `kb_document`, `kb_document_version`, `policy_rule_set`, `model_version`, `org`, `user`,
  `auth_session`, `queue`, `triage_run`, `retention_run`, `audit_partition`, `key`, `feedback_export`).
  `target_id` is the row id when one exists (its type is not fixed by the spec, AE-04). Otherwise it is null, and the
  natural key (`doc_key`, `kid`, `key_id`, partition name) goes in `details`.
* **`request_id`**: the request's ULID for API actions, or the job/run id for system actions.
* **`ip`**: the client IP from the trusted `X-Real-IP` set by Caddy (`CF-Connecting-IP` when Cloudflare Phase 2
  proxies; C-CFG-07). Null for system, policy and service actions. IP is stored only in this column, never inside
  `details`.
* **`details`** is a JSON object of at most 8 KB (proposed), following §4. It always includes `actor_role` for
  `user` actors (a snapshot, so later role changes don't rewrite history) and `is_demo` when the actor is a demo
  account.
* **Transactionality (proposed):** the audit row is written **in the same database transaction** as the change it
  records, so a committed change always has its audit row. Denied or failed attempts are audited in their own
  transaction.

---

## 3. Hash chain and checkpoints

* `hash = SHA-256(prev_hash ‖ canonical_json(row without hash))`, where `canonical_json` is RFC 8785 JCS
  (proposed). The genesis `prev_hash` is 32 zero bytes, per org.
* **Checkpoints (spec §10):** an `audit_chain_checkpoints` row records a period's `first_audit_id`, `last_audit_id`,
  `last_hash`, `row_count` and the `exported_uri` of its off-host copy. Reasons:
  * `partition_drop`: before the retention job drops a partition older than 1 year;
  * `demo_reset`: at step 3 of the nightly demo reset (spec §24.4);
  * `monthly`: at each month end.

  The first entry after a checkpoint chains from its `last_hash`, so verification can restart from a trusted anchor,
  and tail truncation becomes detectable against the off-host copy.
* **Serialised appends (proposed; AE-03):** a transaction-scoped advisory lock on the org's chain, so concurrent
  writers can't fork it.
* A daily verifier job (`job:audit_verify`) recomputes the chain from the latest checkpoint and writes
  `audit.chain_verify_failed` on a mismatch. It also logs to stdout, in case the table itself is compromised.

---

## 4. Redaction rules for `details`

**Never stored:**
* passwords (current or new) and activation secrets;
* access, refresh, CSRF or service tokens. Never the values of the `__Host-Http-tw_access`, `__Host-tw_csrf` or
  `__Secure-tw_refresh` cookies, nor any `Cookie`, `Set-Cookie`, `Authorization` or `x-api-key` value;
* API keys, private keys, KEK/DEK material, HMAC keys, secrets;
* raw or masked ticket and message text, draft text (`final_text`), handoff content, feedback `edited_text`;
* customer e-mail, PII-map values;
* the IP address (it lives in the `ip` column).

**Stored instead:**
* **hashes**: `final_text_sha256`, `content_sha256`, `rules_sha256`, `export_sha256`;
* lengths, counts, enums and ids (including `family_id`, `key_id`, `kid`);
* before/after values of *non-secret* configuration fields;
* `email_hmac`: HMAC-SHA256 of the normalised login e-mail under a server-side key, used to correlate failed logins
  against unknown accounts without storing the raw input.

**Free text** (`justification`, `reason`, `outcome`, `lint_override_reason`, `approval_bypass_reason`) is stored only
where needed for accountability:
* ≤ 500 characters (≤ 200 where noted);
* passed through the same regex PII scrubber as logs (spec §12.10);
* marked `"scrubbed": true`.

**User agent:** only on `auth.*` events, as the `ua_summary` (browser family and OS), never the full string.

---

## 5. Actor types

| `actor_type` | When | `actor_user_id` | `details` must include |
|---|---|---|---|
| `user` | An authenticated human acted, or an unauthenticated login, activation or demo-login attempt was made | The acting user; **null** for failed logins against unknown accounts | `actor_role` (snapshot), `is_demo` |
| `service` (new in v1.1) | A service principal acted through the internal listener (service JWT) | Null | `principal` (e.g. `svc:email-feed`) |
| `system` | Scheduled jobs, workers, integrity checks, scripts | Null. For `auth.refresh_reuse_detected` it is the token owner | `principal`, e.g. `job:retention`, `job:audit_verify`, `job:demo_reset`, `script:reindex`, `script:restore`, `script:rotate_keys`, `script:seed` |
| `policy` | The policy engine created a record for a ticket (e.g. a forced escalation) | Null | `policy_version`, `rules_fired` (rule ids only), `deciding_rule_id` |

---

## 6. Event catalogue (`audit_log`)

Unless a row says otherwise:
* **retention is 1 year** (A-25(m));
* **readers are `admin` and `ops_lead`** (spec §11);
* rows marked † are proposed for tighter read access (§9, AE-06);
* rows marked **(new)** were added for spec v1.1.

### 6.1 Authentication and sessions (P4; admin revoke P7; demo-login P11)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `auth.login_success` † | `POST /auth/login` → 204 (new session family) | user | `user` | `actor_role`, `family_id`, `password_rehashed` (bool), `ua_summary` | — (metric) |
| `auth.login_failed` † | `POST /auth/login` → 401 | user (`actor_user_id` null if unknown) | `user` or null | `reason` ∈ {`bad_credentials`, `unknown_account`, `account_disabled`, `account_inactive`, `backoff_active`}, `email_hmac`, `consecutive_failures`, `ua_summary` | Burst: > 5 per account or > 20 overall in 5 min |
| `auth.account_disabled_failures` † (new) | The 100th consecutive failure hard-disables the account (C-AUTH-02; not for demo accounts) | system (`job:auth`) | `user` | `consecutive_failures`, `first_failure_at` | **High** |
| `auth.logout` † | `POST /auth/logout` | user | `auth_session` (family) | `family_id`, `revoked_sid_written` (bool), `clear_site_data` (bool) | — |
| `auth.refresh_reuse_detected` † | `POST /auth/refresh` presents a rotated token outside the 10 s race grace | system (owner in `actor_user_id`) | `auth_session` (family) | `family_id`, `family_size_revoked`, `seconds_since_rotation`, `ua_changed` (bool), `reuse_count` | **High**: possible token theft |
| `auth.password_changed` † | `POST /auth/change-password` → 204 | user | `user` | `other_sessions_revoked` (count), `hash_params` (e.g. `argon2id m=65536 t=3 p=1`) | — |
| `auth.password_change_failed` † | Wrong current password, policy rejection or breached password | user | `user` | `reason` ∈ {`wrong_current_password`, `too_short`, `too_long`, `context_word`, `breached_offline`, `breached_hibp`, `rate_limited`, `demo_locked`} | > 5 per hour per user |
| `auth.account_activated` † (new) | `POST /auth/activate` → 204 (admin-created user sets the first password) | user | `user` | `activation_age_s`, `family_id` of the first session | — |
| `auth.activation_failed` † (new) | Activation refused | user (null if the secret matches no user) | `user` or null | `reason` ∈ {`unknown_secret`, `expired`, `already_used`, `password_rejected`}, `ua_summary` | Burst per IP |
| `auth.demo_login` † (new) | `POST /auth/demo-login {role}` → 204 (demo mode only) | user (the seeded demo user) | `user` | `role`, `family_id`, `turnstile` ∈ {`passed`, `not_enabled`} | Burst per IP (also rate limited) |
| `auth.session_revoked` † (new) | `POST /auth/sessions/{family_id}:revoke` (own session, after re-authentication) | user | `auth_session` | `family_id`, `was_current` (bool) | — |
| `auth.sessions_revoked` † (new) | `POST /auth/sessions:revoke-others` (after re-authentication) | user | `user` | `revoked_family_count` | — |
| `admin.user_sessions_revoked` (new) | `POST /admin/users/{id}/sessions:revoke` (admin; `DEMO_LOCKED` in demo) | user (admin) | `user` | `revoked_family_count`, `reason` (≤ 200, scrubbed) | Info |
| `admin.sessions_revoked_all` (new) | `POST /admin/sessions:revoke-all` (admin; `DEMO_LOCKED` in demo) | user (admin) | `org` | `revoked_family_count`, `affected_user_count`, `reason` (≤ 200, scrubbed) | **High** (mass logout) |
| `auth.service_token_rejected` † | A service JWT with a bad signature, `aud`, `iss`, `typ` or expiry; a service token on the public listener; or a user token on the internal listener | system | null | `reason`, `kid`, `aud_seen`, `listener` ∈ {`public`, `internal`} | **Always**: never expected in normal operation |

Revocations caused by other actions are recorded in the triggering event (`auth.password_changed`, `user.update`,
`user.delete`, `auth.refresh_reuse_detected`) rather than in a separate row. Listing one's own sessions
(`GET /auth/sessions`) is a read and goes to the security log only (§7).

### 6.2 PII access (P4)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `pii.reveal` | `POST /tickets/{id}/reveal-pii` → 200 | user | `ticket` | `actor_role`, `basis` ∈ {`queue_member`, `admin`}, `fields_revealed` ⊆ {`message`, `customer_email`, `thread`}, `justification` (≤ 500, scrubbed) | > 5 reveals per hour per user (the hard limit is 10/h) |
| `pii.reveal_denied` | Reveal refused (403/429/422) | user | `ticket` | `reason` ∈ {`not_queue_member`, `role_not_permitted`, `rate_limited`, `missing_justification`} | Repeated denials by the same user |

### 6.3 Tickets (P4; purge endpoint P4, closes PR-010 in P9)

Creating a single ticket is **not** audited. It is high-volume and already recorded in `tickets` and
`processing_jobs`.

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `ticket.batch_create` | `POST /tickets/batch` (admin; seeding; `DEMO_LOCKED` in demo) | user | `org` | `count`, `first_ticket_id`, `source` | — |
| `ticket.update` | `PATCH /tickets/{id}` | user | `ticket` | `changed`: {`status`, `assigned_to`, `current_queue`} as `[from, to]`; `feedback_event_id` when a queue change auto-records an override | — |
| `ticket.override` | `POST /tickets/{id}/triage:override` | user | `triage_run` | `ticket_id`, `field`, `from_value`, `to_value`, `comment_present` (bool), `feedback_event_id` | — |
| `ticket.reprocess` | `POST /tickets/{id}/reprocess` | user | `ticket` | `reason` (≤ 200, scrubbed), `new_job_id`, `previous_triage_run_id` | — |
| `ticket.purged` | `DELETE /tickets/{id}` → `tw_purge_ticket()` (admin; `DEMO_LOCKED` in demo) | user | `ticket` | **Tombstone**: `purged_columns` (the full scope: raw and masked text, e-mail, thread, PII map, drafts and citation quotes, feedback text, handoff content, triage output, retrieval query), `row_counts` per table, `ledger_id`, `reason` (≤ 200, scrubbed) | Info |

### 6.4 Drafts (P6)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `draft.approve` | `POST /drafts/{id}/approve` ("Approve & mark sent"; never sends, S-01) | user | `draft` | `ticket_id`, `result` ∈ {`approved`, `edited_and_approved`}, `final_text_sha256`, `final_text_len`, `edit_distance_ratio`, `guard_flags[]`, `acknowledged_warnings`, `needs_human_review`, `policy_decision`, `deciding_rule_id`, `provider`, `model_version_id` | — |
| `draft.approve_blocked` | Approval refused: 403 without queue membership on a `needs_human_review` ticket (A-25(k)), or 422/409 preconditions | user | `draft` | `reason` ∈ {`not_queue_member`, `warnings_not_acknowledged`, `invalid_status`} | Repeated attempts by the same user |
| `draft.reject` | `POST /drafts/{id}/reject` | user | `draft` | `ticket_id`, `reason` (≤ 500, scrubbed) | — |
| `draft.regenerate` | `POST /tickets/{id}/drafts:regenerate` | user | `ticket` | `mode`, `prior_draft_id`, `new_job_id`, `frontier_refused` (bool) | — |

### 6.5 Escalations and handoffs (P7)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `escalation.create` | `POST /tickets/{id}/escalations` (agent) **or** a forced policy escalation | user or policy | `escalation` | `ticket_id`, `target`, `reasons[]` (escalation-reason enum), `handoff_id`, `handoff_variant`; for policy: `policy_version`, `rules_fired[]`, `deciding_rule_id` | — |
| `escalation.ack` | `POST /escalations/{id}/acknowledge` | user | `escalation` | `target`, `seconds_to_ack` | — |
| `escalation.resolve` | `POST /escalations/{id}/resolve` | user | `escalation` | `target`, `outcome` (≤ 500, scrubbed), `seconds_to_resolve` | — |
| `handoff.edit` | `PUT /escalations/{id}/handoff` (creates a new version) | user | `handoff_brief` | `escalation_id`, `version_from`, `version_to`, `changed_fields[]` (names only), `completeness_ok` (bool) | — |
| `handoff.auto_create` | Rule N2 (high churn + high value) auto-creates a CSM handoff draft | policy | `handoff_brief` | `ticket_id`, `variant` = `csm`, `reason` = `high_churn_risk_high_value`, `policy_version` | — |

### 6.6 Feedback (P7)

Feedback events are stored append-only in `feedback_events`. Only safety-relevant flags and exports are audited.

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `feedback.flag` | `POST /feedback` with `action=flag` and `flag_reason` ∈ {`pii_leak`, `unsafe`, `hallucination`} | user | target of the flag | `flag_reason`, `feedback_event_id`, `model_version_id` | `pii_leak` and `unsafe` → security dashboard |
| `feedback.export` (new) | `GET /admin/feedback/export?from&to` (admin; `DEMO_LOCKED` in demo) | user (admin) | `feedback_export` | `from`, `to`, `row_count`, `excluded_anthropic_count` (A-01), `export_sha256`, `filename` (server-generated) | Info; unusual volume |

### 6.7 Knowledge base (P5; lint P6)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `kb.create` | `POST /kb/documents` (creates v1 as draft) | user | `kb_document` | `doc_key`, `doc_type`, `version` = 1, `content_sha256`, `body_len`, `sanitizer_modified` (bool), `lint_hits` (counts by type) | — |
| `kb.version_create` | `POST /kb/documents/{doc_key}/versions` | user | `kb_document_version` | `doc_key`, `version`, `content_sha256`, `sanitizer_modified`, `lint_hits` | — |
| `kb.submit` | `POST …/versions/{v}/submit` (→ `in_review`) | user | `kb_document_version` | `doc_key`, `version`, `content_sha256` | — |
| `kb.approve` | `POST …/versions/{v}/approve` with four-eyes and a clean lint (→ `approved`; triggers chunk + embed + index; `DEMO_LOCKED` in demo) | user | `kb_document_version` | `doc_key`, `doc_type`, `version`, `content_sha256`, `submitted_by`, `chunks_indexed`, `supersedes_version` | — |
| `kb.approve_with_lint_override` | Approval of a version whose lint found hits, with a recorded justification (spec §8.2) | user | `kb_document_version` | as `kb.approve` + `lint_hits`, `lint_override_reason` (≤ 500, scrubbed) | **Always** (security review) |
| `kb.approve_bypass` | Four-eyes bypass with `approval_bypass_reason`, used only by the seed/reset job (spec §10) | system (`script:seed` or `job:demo_reset`) | `kb_document_version` | as `kb.approve` + `approval_bypass_reason` (≤ 200) | **High** if the actor is not the seed/reset job |
| `kb.approve_denied` | Approval refused (self-approval, wrong role, invalid state, lint hit without justification) | user | `kb_document_version` | `reason` ∈ {`self_approval`, `role_not_permitted`, `invalid_state`, `lint_unjustified`, `demo_locked`} | Always (possible four-eyes bypass attempt) |
| `kb.retire` | `POST /kb/documents/{doc_key}/retire` (`DEMO_LOCKED` in demo) | user | `kb_document` | `doc_key`, `retired_version`, `reason` (≤ 200, scrubbed) | — |
| `kb.reembed` | `scripts/reindex.py` full re-embed after an embedding-model change (ADR-0008) | system (`script:reindex`) | `org` | `embedding_model_from`, `embedding_model_to`, `chunk_count`, `index_version` | — |

### 6.8 Queues, routing and policy rules (P7)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `queues.update` | `PATCH /queues/{key}` | user | `queue` | `queue_key`, `changed`: {`display_name`, `description`, `sla_policy`, `is_active`} as `[from, to]` | — |
| `rules.create` | `POST /policy/rule-sets` | user | `policy_rule_set` | `version`, `based_on_version`, `rules_sha256`, `thresholds` {`tau_intent`, `tau_queue`, `tau_ret`, `tau_crit`, `tau_inj`, `tau_entail`, `tau_contra`, `tau_conflict`, `pii_heavy_min`}, `lexicon_versions` | — |
| `rules.activate` | `POST /policy/rule-sets/{id}/activate` (`DEMO_LOCKED` in demo; dry-run allowed) | user | `policy_rule_set` | `version`, `previous_active_version`, `dry_run` {`golden_total`: 60, `decisions_changed`, `forced_escalation_ok`}, `justified_by_eval_run_id` | Info to ops |
| `rules.activate_rejected` | Dry-run failure or safety-floor violation (proposed) | user | `policy_rule_set` | `version`, `failing_golden_ids[]` (≤ 20), `safety_floor_violations[]` | Always |

### 6.9 Models (P7; integrity from P4)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `model.register` | New `model_versions` row (registration script or admin) | system or user | `model_version` | `registry_name`, `semver`, `alias`, `gguf_sha256`, `adapter_hf_revision`, `eval_run_id` | — |
| `model.activate` | `POST /admin/models/{id}/activate`, including rollback (`model-rollback.md`; `DEMO_LOCKED` in demo) | user | `model_version` | `registry_name`, `semver`, `previous_production_id`, `eval_run_id`, `thresholds_met` (true), `gguf_sha256`, `rollback` (bool) | Info |
| `model.activate_rejected` | Activation refused | user | `model_version` | `reason` ∈ {`thresholds_not_met`, `sha_mismatch`, `missing_eval_run`, `taxonomy_mismatch`, `demo_locked`} | Always |
| `model.integrity_check_failed` | Load or readiness finds a GGUF sha256 or served-model digest mismatch | system | `model_version` | `source` ∈ {`gguf_file`, `ollama_digest`}, `expected_sha256_prefix`, `observed_sha256_prefix` | **Critical** |

### 6.10 Organisation settings and frontier (P7)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `org_settings.update` | `PATCH /admin/org-settings` (`DEMO_LOCKED` in demo) | user | `org` | `changed`: {`frontier_enabled`, `vendor_review_ack`, `frontier_daily_budget_usd`} as `[from, to]` | When `frontier_enabled` becomes true or the budget increases |
| `frontier.budget_exhausted` | The daily frontier spend reaches `TW_FRONTIER_DAILY_BUDGET_USD` | system | `org` | `budget_usd`, `spent_usd`, `date`, `calls_today` | Yes (`frontier-budget-exhausted.md`) |

### 6.11 Users and roles (P4 model; admin API P7)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `user.create` | `POST /admin/users` (returns a one-time activation link/code; `DEMO_LOCKED` in demo) | user (admin) | `user` | `role`, `is_active`, `email_domain` (domain only), `activation_expires_at` | — |
| `user.update` | `PATCH /admin/users/{id}` (a role change or disable revokes all of the user's sessions) | user (admin) | `user` | `changed`: {`role`, `is_active`} as `[from, to]`, `display_name_changed` (bool), `sessions_revoked` (count) | Role changed **to** `admin` |
| `user.unlocked` (new) | Audited admin unlock after the 100-failure hard disable | user (admin) | `user` | `consecutive_failures_cleared`, `disabled_since` | Info |
| `user.delete` | `DELETE /admin/users/{id}` (soft delete) | user (admin) | `user` | `soft_delete` (true), `sessions_revoked` (count) | — |
| `user.activation_reissued` (proposed, G-13) | Admin re-issues an activation secret for a forgotten password | user (admin) | `user` | `activation_expires_at`, `sessions_revoked` (count) | Info |

### 6.12 Demo mode (P11)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `demo.locked_denied` (new) | A demo account calls a privileged route → `403 DEMO_LOCKED` | user (demo account) | route's target type, or `org` | `route` (template), `method`, `first_seen_at`, `count` | Spike (possible probing) |
| `demo.reset_completed` | Step 8 of the nightly reset (spec §24.4), after the smoke test passes | system (`job:demo_reset`) | `org` | `golden_dump_sha256`, `audit_rows_exported`, `ledger_rows_exported`, `checkpoint_id` (reason `demo_reset`), `sessions_flushed` (bool), `smoke_passed` (true), `maintenance_seconds` | On failure (the job alerts and follows `demo-reset.md`) |

`demo.locked_denied` is **deduplicated** to one row per (session family, route, hour), with a `count`, so a scripted
visitor cannot flood the hash-chained table. Every denial also goes to the security log (§7).

### 6.13 Data lifecycle and cryptography (P4 DEKs; P9 shred, restore)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `retention.purge` | Nightly `retention_job` | system (`job:retention`) | `retention_run` | `cutoffs` per category, `raw_rows_nulled` (`tw_retention_purge()`), `periods_shredded[]`, `llm_calls_partitions_dropped[]`, `audit_partitions_dropped[]` (each with its `checkpoint_id`), `idempotency_keys_purged`, `revoked_sessions_purged` | On job failure |
| `crypto.dek_created` (new) | First use of a new period DEK | system | `key` | `key_id` (e.g. `dek-2026-10`), `kek_id` | — |
| `crypto.dek_destroyed` (new) | `tw_shred_period()` destroys a period DEK (crypto-shred) | system (`job:retention`) | `key` | `key_id`, `newest_row_at`, `ledger_id` | Info |
| `crypto.kek_rotated` (new) | KEK rotation (`rotate-secrets.md`) | system (`script:rotate_keys`) | `key` | `kek_id_from`, `kek_id_to`, `deks_rewrapped` | Info |
| `crypto.dek_rewrapped` (new) | DEKs re-wrapped under a new KEK (one row per rotation batch) | system (`script:rotate_keys`) | `key` | `kek_id_to`, `key_ids[]` | — |
| `restore.ledger_replayed` (new) | `scripts/restore.sh` re-applied the off-host deletion ledger, before the restored database serves traffic | system (`script:restore`) | `org` | `backup_id`, `backup_taken_at`, `ledger_entries_replayed`, `purges_reapplied`, `shreds_reapplied`, `chain_verified` (bool), `operator` (host account name) | Always |

### 6.14 Integrity and signing keys (P9)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `audit.chain_verify_failed` | Chain verification finds a mismatch | system (`job:audit_verify`) | `audit_partition` | `partition`, `first_bad_id`, `checkpoint_id`, `expected_prev_hash_prefix` | **Critical** (also emitted to stdout) |
| `security.key_rotated` | `rotate-secrets.md` procedure (rotation script) | system (`script:rotate_keys`) | `key` (`kid` in details) | `key_type` ∈ {`user_jwt_signing`, `service_jwt_signing`, `csrf_hmac`, `login_throttle_hmac`}, `new_kid`, `retired_kid`, `emergency` (bool; revokes all sessions) | Emergency rotation: **High** |

### 6.15 Audit access (P7)

| Action | Trigger | Actor | Target | `details` (redacted) | Alert |
|---|---|---|---|---|---|
| `audit.query` | `GET /admin/audit-log` (one row per query, proposed) | user | `org` | `filters` {`action`, `target_type`, `from`, `to`}, `result_count` | — |

### 6.16 Coverage cross-check (privileged routes and jobs → audit actions)

| Route / job (spec §10, §11, §24) | Action(s) |
|---|---|
| `POST /auth/login`, `/auth/refresh` (reuse), `/auth/logout`, `/auth/change-password`, `/auth/activate`, `/auth/demo-login` | `auth.*` |
| `POST /auth/sessions/{family_id}:revoke`, `/auth/sessions:revoke-others` | `auth.session_revoked`, `auth.sessions_revoked` |
| `POST /admin/users/{id}/sessions:revoke`, `/admin/sessions:revoke-all` | `admin.user_sessions_revoked`, `admin.sessions_revoked_all` |
| Internal listener `POST /tickets` (service token) | `auth.service_token_rejected` on failure; accepted ingestion is not audited (system of record: `tickets`) |
| `POST /tickets/{id}/reveal-pii` | `pii.reveal`, `pii.reveal_denied` |
| `PATCH /tickets/{id}`, `POST /tickets/{id}/triage:override`, `/reprocess`, `/drafts:regenerate`, `DELETE /tickets/{id}`, `POST /tickets/batch` | `ticket.*`, `draft.regenerate` |
| `POST /drafts/{id}/approve`, `/reject` | `draft.*` |
| `POST /tickets/{id}/escalations`, `PUT /escalations/{id}/handoff`, `POST /escalations/{id}/acknowledge`, `/resolve` | `escalation.*`, `handoff.edit` |
| `POST /feedback` (flags only); `GET /admin/feedback/export` | `feedback.flag`, `feedback.export` |
| `POST /kb/documents`, `/versions`, `/submit`, `/approve`, `/retire` | `kb.*` |
| `PATCH /queues/{key}`; `POST /policy/rule-sets`, `/{id}/activate` | `queues.update`, `rules.*` |
| `POST /admin/models/{id}/activate` | `model.activate`, `model.activate_rejected` |
| `PATCH /admin/org-settings` | `org_settings.update` |
| `POST/PATCH/DELETE /admin/users`; admin unlock | `user.*` |
| `GET /admin/audit-log` | `audit.query` |
| Any `DEMO_LOCKED` denial | `demo.locked_denied` (deduplicated) |
| Jobs: retention and shred, audit verify, demo reset, reindex, restore, key and KEK rotation, frontier budget, seed | `retention.purge`, `crypto.*`, `audit.*`, `demo.reset_completed`, `kb.reembed`, `kb.approve_bypass`, `restore.ledger_replayed`, `security.key_rotated`, `frontier.budget_exhausted` |
| **Not audited by design** (system of record elsewhere): single `POST /tickets`, `PUT /drafts/{id}` autosave, `POST /feedback` (non-flag), `GET` reads other than reveal, export and audit queries, `GET /auth/sessions` (security log), pipeline steps, research publishing | `tickets`, `drafts`, `feedback_events`, `policy_decisions`, `llm_calls`; git history |

---

## 7. Security events (structured log + metrics; not in `audit_log`)

These are high-volume signals. Storing them in the hash-chained table would add noise and write contention without
adding accountability. Each is a structured log line (`event=<name>`, `request_id`, route, hashed user id, reason
enum) plus a Prometheus counter. They are kept **1 year** and shipped off-host (A-25(m)).

| Event | Trigger | Fields (no PII) | Metric | Alert |
|---|---|---|---|---|
| `authz.denied` | 403 `FORBIDDEN`, or 404 for an out-of-scope object | route, `required_roles`, `actor_role`, `target_type`, `kind` ∈ {`forbidden`, `out_of_scope`} | `tw_http_requests_total{status="403"}` | Spike per user or overall |
| `demo.locked` | Every `403 DEMO_LOCKED` response (the audit row is deduplicated) | route, `actor_role` | `tw_demo_locked_total` (proposed) | Spike |
| `csrf.failed` | 403 `CSRF_FAILED` | route, `reason` ∈ {`fetch_metadata`, `origin`, `origin_missing`, `token_missing`, `token_mismatch`, `token_sid_mismatch`} | `tw_csrf_failures_total` | Spike |
| `media_type.rejected` | 415 `UNSUPPORTED_MEDIA_TYPE` | route, content-type family | `tw_http_requests_total{status="415"}` | Spike |
| `auth.jwt_invalid` | 401 on an invalid or expired access token | `reason` ∈ {`expired`, `signature`, `audience`, `issuer`, `typ`, `unknown_kid`, `alg`, `forbidden_header`} | `tw_auth_failures_total{kind}` | Spike in `signature`/`alg`/`forbidden_header` |
| `auth.sid_revoked` | A request carrying a revoked `sid` | `reason` ∈ {`logout`, `admin`, `password_change`, `role_change`, `disabled`} | `tw_auth_failures_total{kind="revoked"}` | Spike |
| `auth.revocation_check_failed` | The Redis revoked-`sid` check failed, so the request failed closed (503 unsafe / 401 reads) | method class | `tw_revocation_check_failures_total` (proposed) | **Any** (auth outage) |
| `auth.refresh_superseded` | 409 `REFRESH_SUPERSEDED` inside the 10 s race grace (nothing issued) | `family_id` | `tw_refresh_superseded_total` (proposed) | Spike |
| `auth.backoff_engaged` | Per-account backoff delays a login (from the 5th consecutive failure) | `consecutive_failures`, `delay_s` | `tw_auth_backoff_total` (proposed) | Sustained |
| `auth.sessions_listed` | `GET /auth/sessions` | `family_count` | — | — |
| `ratelimit.exceeded` | 429 `RATE_LIMITED` | route, `key_type` ∈ {`ip`, `user`, `session`, `global`, `queue_depth`} | `tw_rate_limited_total` | Sustained |
| `validation.failed` | 422 `VALIDATION_ERROR` | route, error `type`s (never input values) | `tw_http_requests_total{status="422"}` | — |
| `body.too_large` | 413 `PAYLOAD_TOO_LARGE` | route, route limit, declared length bucket | `tw_http_requests_total{status="413"}` | Spike |
| `sse.rejected` | SSE refused or closed (401/404/429; revoked `sid` on heartbeat) | `reason` ∈ {`unauthenticated`, `out_of_scope`, `per_ticket_limit`, `revoked`} | `tw_sse_rejected_total` (proposed) | Spike |
| `pii.mask_failed` | Masking timeout or exception → P7 `pii_masking_failed` (fail closed) | `ticket_id`, `stage`, `error_code` | `tw_pii_mask_failures_total` (proposed) | Any |
| `pii.residual_blocked` | The residual gate (hit ≥ 0.6) blocked the frontier | `ticket_id`, entity types | `tw_pii_residual_total` | Spike |
| `injection.suspected` | Rule P0 fired | `ticket_id`, `detector` ∈ {`lexicon`, `prompt_guard_2`}, score bucket, sanitizer counts | `tw_escalation_reasons_total{reason="prompt_injection_suspected"}` | Spike |
| `kb.lint_hit` | KB lint found injection or hidden-content hits at submit | `doc_key`, `version`, hit types | `tw_kb_lint_hits_total` (proposed) | Any on `known_incident` docs |
| `guard.flagged` | A claim guard set a flag on a draft | `draft_id`, `guard_flags[]` | `tw_guard_flags_total{flag}` (proposed) | Spike in `contains_pii` / `injection_echo` |
| `email_feed.rejected` | Unparseable, oversized or quarantined feed file | file-name hash, `reason`, `attachments_dropped` | `tw_email_feed_rejected_total` (proposed) | Spike |
| `egress.denied` (new) | The egress proxy denied a destination (proxy log, ADR-0036) | `source_container`, `dest_host`, `dest_port` | `tw_egress_denied_total` (proposed) | **Any** outside model-fetch windows |
| `frontier.circuit_open` | The frontier breaker opened | `provider`, `last_error_code`, `open_for_s` | `tw_llm_calls_total{status="circuit_open"}` | Yes |
| `frontier.spend_limit_reached` (new) | The vendor workspace spend limit rejected a call (spend-limit breaker) | `provider`, `workspace` | `tw_frontier_spend_limit_total` (proposed) | Yes |
| `frontier.refusal` | A frontier response ended with a refusal stop reason; local fallback used | `ticket_id`, `provider` | `tw_llm_calls_total{status="error",code="refusal"}` | Spike |
| `kb.index_lag` | A process's BM25 index version lags the latest publish | process id, lag seconds | `tw_bm25_index_version` | Yes |

---

## 8. Alerting summary

Alerts are Prometheus recording rules plus Grafana alerting, **delivered by e-mail or ntfy** (A-25(m); rules in spec
§15). The outbound path for delivery is not yet on the egress allow-list (threat model OI-14).

| Alert | Source | Severity | Runbook |
|---|---|---|---|
| Refresh-token reuse detected | `auth.refresh_reuse_detected` | High | `security-incident.md` |
| Login-failure burst, backoff surge or hard disable | `auth.login_failed`, `auth.backoff_engaged`, `auth.account_disabled_failures` | Medium / High | `security-incident.md` |
| Mass session revocation | `admin.sessions_revoked_all` | High | `security-incident.md` |
| Revocation check failing (auth outage) | `auth.revocation_check_failed` | High | `security-incident.md` |
| Service-token rejection | `auth.service_token_rejected` | High | `security-incident.md`, `rotate-secrets.md` |
| CSRF failures spike | `csrf.failed` | Medium | `security-incident.md` |
| PII-reveal burst or repeated denials | `pii.reveal`, `pii.reveal_denied` | Medium | `security-incident.md` |
| KB lint override or unexpected four-eyes bypass | `kb.approve_with_lint_override`, `kb.approve_bypass` (non-seed actor), `kb.approve_denied` | High | `security-incident.md` |
| Rule-set activation rejected | `rules.activate_rejected` | Medium | — (review the diff) |
| Model integrity failure | `model.integrity_check_failed` | **Critical** | `model-rollback.md`, `security-incident.md` |
| Audit chain broken | `audit.chain_verify_failed` | **Critical** | `security-incident.md`, `restore-db.md` |
| Egress denial | `egress.denied` | High | `security-incident.md` |
| Frontier enabled, budget raised or exhausted, spend limit reached | `org_settings.update`, `frontier.budget_exhausted`, `frontier.spend_limit_reached`, budget < 20% | Medium | `frontier-budget-exhausted.md` |
| Demo probing | `demo.locked_denied`, `demo.locked` spike | Low | `demo-reset.md` |
| Demo reset failed | the reset job (no `demo.reset_completed`) | High | `demo-reset.md` |
| Role elevated to admin | `user.update` | Medium | — (confirm with admin) |
| Safety flags from agents (`pii_leak`, `unsafe`) | `feedback.flag` | Medium | `security-incident.md` |
| Masking failures | `pii.mask_failed` | Medium | pipeline runbooks |
| Restore performed | `restore.ledger_replayed` | Info | `restore-db.md` |

---

## 9. Access control and retention

* **Readers (spec):** `admin` (all) and `ops_lead` (read), through `GET /api/v1/admin/audit-log`, with entries
  identified by `public_id` (spec §11). Nobody can modify or delete audit rows through the API. `tw_app` has
  INSERT/SELECT only on `audit_log`, `audit_chain_checkpoints` and `deletion_ledger` (spec §10).
* **Proposed least-privilege refinements (AE-06; need a spec/RBAC update):**
  * † `auth.*` events, and the `ip` / `ua_summary` fields of all events, readable by `admin` only. `ops_lead` sees
    those rows with `ip` and `ua_summary` redacted.
  * `tw_readonly` (the dashboard role) gets **no** SELECT on `audit_log`, `audit_chain_checkpoints` or
    `deletion_ledger`. Security dashboards use the Prometheus metrics in §7.
  * Reading the audit log is itself audited (`audit.query`).
* **Retention:** 1 year for `audit_log` rows and the security log (A-25(m)). Monthly partitions are dropped by the
  nightly `retention_job` only after the off-host export and a `partition_drop` checkpoint. Tombstones
  (`ticket.purged`) follow the same 1-year retention. The deletion ledger's own retention is not specified (AE-11).
* **Off-host shipping:** security and audit events go to a logically separate sink (service chosen at P9). The
  minimum is a nightly encrypted off-host copy of the audit partitions, which also carries the deletion ledger
  (spec §12.10; EX-05 if not in place by P9).
* **Demo mode (spec §24.4):** the nightly reset exports the audit rows and ledger rows written since the previous
  reset, writes a `demo_reset` checkpoint, and restores the golden dump **excluding** `audit_log`,
  `audit_chain_checkpoints` and `deletion_ledger`. Those are preserved across resets, and the chain continues from the
  checkpoint. The public demo therefore keeps a continuous trail of what visitors did.
* **Backups and restore:** `audit_log` is in the nightly dump. A restore rolls the table back to the backup point, so
  `scripts/restore.sh` re-applies the off-host deletion ledger before serving and writes `restore.ledger_replayed`.
  Audit rows written after the backup survive in the off-host copy, and chain verification against the latest
  exported checkpoint shows the gap.

---

## 10. Verification

| Test | What it proves | Planned location | Phase |
|---|---|---|---|
| `T-AUDIT-coverage` | Every privileged route and job in §6.16 writes exactly one audit row with the correct `action`, `actor_type`, `target_type`/`target_id` and required `details` keys. A route-registry test fails if a mutating route has neither an audit mapping nor an explicit `audit_exempt` reason | `backend/tests/integration/test_audit.py` | P4 → P11 |
| `T-SEC-AUDIT-append-only` | Connected as `tw_app`, UPDATE/DELETE/TRUNCATE on `audit_log`, `audit_chain_checkpoints` and `deletion_ledger` fail | `backend/tests/integration/test_audit.py` | P4 |
| `T-SEC-AUDIT-chain-verify` | The verifier accepts a clean chain, reports the first bad id after a superuser edit, and continues correctly across a `partition_drop` or `demo_reset` checkpoint | `backend/tests/integration/test_audit.py` | P9 |
| `T-SEC-AUDIT-redaction` | Across all audit rows produced by the integration suite, `details` contains no fixture PII, ticket text, tokens, cookie values, secrets or IP addresses | `backend/tests/integration/test_audit.py` | P4 |
| `T-SEC-METRICS-events` | Each §7 security event increments its metric and emits a structured log line without PII | `backend/tests/integration/test_security_metrics.py` | P7 |
| `T-SEC-DEMO-reset` | Audit tables and the ledger survive the reset; the `demo_reset` checkpoint is written; `demo.reset_completed` follows the smoke test | `tests/e2e-stack/test_demo_reset.py` | P11 |
| `T-SEC-DEMO-locked` | Each `DEMO_LOCKED` denial writes a deduplicated `demo.locked_denied` row and a `demo.locked` log line | `backend/tests/integration/test_demo_mode.py` | P11 |
| `T-RESTORE-ledger` | After a restore, the ledger replay runs before serving, and `restore.ledger_replayed` records the counts | `tests/e2e-stack/test_restore.py` | P9 |
| `T-FEEDBACK-export` | `feedback.export` is written with `row_count` and `excluded_anthropic_count` | `backend/tests/integration/test_feedback_export.py` | P7 |
| `T-SEC-CRYPTO-shred` | `crypto.dek_destroyed` and the ledger row are written on a period shred | `backend/tests/integration/test_encryption_at_rest.py` | P9 |

---

## 11. Open items (spec clarifications; the spec is not edited here)

Resolved by spec v1.1:
* AE-01: `audit_log.id` is now bigint identity + `public_id`.
* AE-02: `audit_chain_checkpoints` added.
* AE-05: security-log retention is 1 year (Prometheus retention is still unspecified; see AE-12).
* AE-07: P7 records `pii_masking_failed`.
* AE-08: alert delivery is Grafana alerting to e-mail or ntfy.
* AE-09: the demo reset preserves the audit tables.

| ID | Item |
|---|---|
| AE-03 | Chain appends need serialisation (advisory lock) under concurrent writers. Still not specified |
| AE-04 | `target_id` type is unspecified (UUID vs bigint targets). This catalogue stores the row id, or null with the natural key in `details` |
| AE-06 | Whether `ops_lead` should see auth events and IP/UA fields (least privilege), and whether `tw_readonly` may read the audit tables |
| AE-10 | `DEMO_LOCKED` denials could flood the hash-chained table. This catalogue deduplicates to one row per (family, route, hour); the spec does not say |
| AE-11 | Retention of `deletion_ledger` (and of `audit_chain_checkpoints`) is not specified |
| AE-12 | Prometheus retention is not specified |
| AE-13 | The outbound path for alert delivery and off-host log shipping is not on the egress allow-list (threat model OI-14) |
