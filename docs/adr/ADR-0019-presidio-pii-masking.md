---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §7, §10; spec §5.6, §5.9, §7.2, §7.3 (P7, N5), §7.5, §7.7, §10, §12.4, §12.5, §12.10, §20 L-13; research pii-masking-presidio
informed: contributors; admin persona (PII reveal)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0019: Presidio PII masking before every model, log and frontier call

> **Amended in spec v1.1 (2026-09-27; change record A-17, W-5).**
> * **Pinned Presidio** (exact version with hashes; 2.2.364 as of 2026-09-26). The project moved to
>   `github.com/data-privacy-stack/presidio`, and the PyPI names are unchanged.
> * **spaCy `en_core_web_md`** by default (31 MB, NER F 0.847, vs 382 MB / 0.855 for lg). The model wheel is installed
>   by URL + sha256 in the lockfile.
> * **Explicit entity list** on every call. **DATE_TIME, UUID, LOCATION and ORGANIZATION are not masked**, because
>   masking them destroys triage entities.
> * Custom recognizers for `tm_live_…`/`tm_test_…` keys, gitleaks-derived secrets and street addresses. The allow-list
>   regexes are **anchored**.
> * **Card numbers are reduced to their last 4 digits before any storage**, including the encrypted raw copy.
> * The map is stored as `pii_map_enc` + `pii_map_key_id` (AAD = ticket id ‖ purpose ‖ key id).
> * **`mask()` runs exactly once** (intentionally not idempotent). This replaces the v1.0 "idempotence" property.
> * Masking failure or timeout emits the reason **`pii_masking_failed`** via rule P7 (fail closed). N5 flags PII-heavy
>   tickets (≥ 8 entities) and disables the frontier. The two schema gaps this ADR flagged are resolved.

## Context and Problem Statement

The brief's architecture puts **"PII masking + customer metadata"** right after an incoming ticket (brief §7). The
spec makes masking a hard precondition for:
* any model call (local SLM, embedder, NLI verifier, injection detector, frontier);
* any log line, trace attribute or Langfuse record (§12.5, §12.10, LLM02:2026).

Entities are never extracted raw. They appear only as typed, indexed placeholders (§5.6).

Masking runs in step 1 of the worker (§7.2), after the sanitizer (NFKC, invisible Unicode) and before any model. It
has a 1 s budget and **fails closed** (P7). The residual-PII re-scan must be clear (no hit ≥ 0.6) before the frontier
is allowed or masked text is persisted. Agents who belong to the ticket's queue (and admins) can reveal the raw text,
and every reveal is audited.

v1.0 over-masked: DATE, UUID and LOCATION masking would destroy `charge_date`, `timestamp`, `workspace_id` and
`region`. It also used an unanchored allow-list, which could un-mask "Okta Smith". And it stored full PANs in the
encrypted copy.

Which PII detection and masking approach, configured how, meets these constraints?

## Decision Drivers

* Data minimisation: no raw PII reaches models, logs, traces or third parties (LLM02:2026; ASVS V14).
* Local processing with no egress of unmasked text (egress allow-list, ADR-0036).
* High recall on structured PII and secrets, and reasonable NER for names and addresses, **without destroying**
  triage entities.
* Deterministic, consistent placeholders across a thread, and a reversible map that never leaves the backend.
* CPU latency ≤ 1 s per ticket, in a bounded worker thread.
* PCI DSS Req. 3-style minimisation of card data (verify against PCI DSS before any real deployment).

## Considered Options

1. Microsoft Presidio (pinned, data-privacy-stack) + spaCy md + explicit entity list + custom recognizers (chosen)
2. scrubadub
3. A cloud DLP service
4. Regex only

## Decision Outcome

Chosen option: "pinned Presidio with an explicit entity list and custom recognizers", because it combines pattern,
checksum (Luhn/IBAN), context-aware scoring and NER locally, and it can be configured to keep the entities triage
needs.

Configuration (spec §12.5):

* **Entities:** PERSON, NRP, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, IBAN_CODE, IP_ADDRESS, URL, CRYPTO,
  MAC_ADDRESS, US_SSN, US_PASSPORT, US_DRIVER_LICENSE, US_ITIN, US_BANK_NUMBER, UK_NHS, TASKMOOR_API_KEY,
  SECRET_TOKEN, STREET_ADDRESS. Startup and CI assert every name is supported, because Presidio silently ignores
  unknown names.
* **Recognizers:** the built-in Luhn and IBAN recognizers (not re-implemented); extended phone regions; Taskmoor keys
  (case-sensitive); gitleaks-derived secrets (AWS, GitHub PATs, Slack, Stripe-style, JWTs, PEM keys); a heuristic
  street-address recognizer (reported only).
* **Allow-list:** anchored `^…$` regexes for `acct_` ids, our own placeholders and product terms (Okta, SCIM, SAML,
  SSO, …).
* **Placeholders:** customer-typed `<TYPE_n>` strings are escaped first. Overlaps resolve by score, then span length.
  Indexes follow reading order and are reused across the thread.
* **Cards:** Luhn-valid PANs are reduced to the last 4 in step 0, before encryption (ADR-0030).
* **Map:** JSON, AES-256-GCM (AAD binds ticket id, purpose and key id), crypto-shredded with the raw text after 90 days
  (ADR-0037). Never sent to models, logs, traces or Langfuse. Decrypted only by `POST /tickets/{id}/reveal-pii`.
* **Residual gate:** `analyze()` re-runs on the masked text. A hit ≥ 0.6 blocks the frontier and is counted
  (`tw_pii_residual_total`). The log scrubber reuses the regex recognizers (no NER per log line).
* **Budget:** a bounded thread under `asyncio.timeout(1.0)`. A timeout or exception gives P7 `pii_masking_failed`,
  with no model calls.
* **N5:** ≥ 8 masked entities (`pii_heavy_min`) adds `pii_heavy_content` and disables the frontier.

**Verify at build (research `pii-masking-presidio`):** the Presidio version, the md vs lg speed difference (measure),
and supported entity names.

### Consequences

* Good, because models, traces, logs and the frontier see masked text only, while dates, UUIDs, regions and company
  names stay available to triage.
* Good, because card data is minimised before storage, even in encrypted form.
* Good, because recognizers are code, reviewed and tested, and fixture recall is a CI gate.
* Bad, because NER is imperfect, and by design dates, UUIDs, cities/countries and company names are not masked
  (L-13). Mitigations: synthetic data only (S-12), the residual gate, fail-closed behaviour, log scrubbing, and N5.
* Bad, because `mask()` is not idempotent, so double masking is a bug that tests must prevent (single call site).
* Neutral, because placeholders change model inputs. Training uses 20% placeholder injection (§9.1 step 7).

### Confirmation

* PII fixture (P4), 200 synthetic tickets. Targets:

  | Entity class | Target |
  |---|---|
  | email / phone / card | recall ≥ 0.95 |
  | API keys and secrets | recall ≥ 0.99 |
  | IBAN | recall ≥ 0.95 |
  | PERSON | recall ≥ 0.90 |
  | hard negatives | false-mask ≤ 2% |
  | street address | reported |

  A 60-case subset runs on every PR and the full 200 nightly. A drop > 2 points fails.
* Unit tests: reading-order numbering, spoofed-placeholder escaping, PAN → last 4, anchored allow-list. A startup
  assertion covers supported entities. Property test: the masked text never contains a gold e-mail or phone.
* `pii/` ≥ 95% branch coverage.
* `T-SEC-PII-fail-closed`: an injected timeout or exception gives P7 `pii_masking_failed`, with zero `llm_calls`
  rows.
* `T-SEC-PII-residual-gate`: a residual hit ≥ 0.6 blocks the frontier.
* `T-SEC-LOG-redaction`: no fixture PII in logs or spans.
* M-08 stage timing for `pii.mask` (the 1 s budget) on the reference box.

## Pros and Cons of the Options

### Presidio (pinned) + spaCy md + explicit list

* Good, because it is local and extensible (pattern, checksum, context, NER), configurable to keep triage entities,
  and open source.
* Bad, because NER has misses and false positives, the project has moved (pin and watch it), and CPU time is needed.

### scrubadub

* Good, because it is lightweight and simple.
* Bad, because it has fewer recognizers, weaker NER integration and less active maintenance (verify).

### Cloud DLP

* Good, because it is accurate and managed.
* Bad, because it sends **unmasked** text to a third party in order to mask it. That breaks the egress allow-list
  and adds a vendor review and a network dependency.

### Regex only

* Good, because it is fast and deterministic.
* Bad, because it cannot find names or free-form addresses reliably, which fails the PERSON and address coverage.

## More Information

* Spec (private): §5.6 (masking scope), §5.9 (`pii_masking_failed`, `pii_heavy_content`), §7.2 (steps 0–1), §7.3
  (P7, N5), §7.5 (condition 6), §7.7, §10 (`tickets.pii_map_enc`, `pii_map_key_id`, `pii_entity_count`), §11
  (reveal), §12.4, §12.5, §12.10, §13 S-12, §20 L-13. Change record A-17, W-5.
* Brief (private): §7, §10. BR-016, BR-035.
* Research: [pii-masking-presidio](../research/pii-masking-presidio.md).
* Related ADRs: ADR-0015 (residual gate), ADR-0024 (redaction), ADR-0030 (encryption), ADR-0037 (crypto-shred of the
  map).
* Revisit when: fixture recall drops, real (authorised) data is introduced, or multilingual support lifts NG-07.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (pinned Presidio, spaCy md, explicit
  entities, anchored allow-list, PAN last-4, `pii_map_enc`, `pii_masking_failed`).
