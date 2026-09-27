---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §4, §5, §9, §10, §11; spec §5 (taxonomy, §5.9 reasons and emitters), §6, §9.1–§9.3, §9.6, §9.8; research synthetic-data-generation
informed: labelers; ops_lead persona; model card readers
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0029: Taxonomy v1: 12 intents plus `other_unclear`, 6 queues

> **Amended in spec v1.1 (2026-09-27; change record W-5, A-04, A-17, A-06, W-m12, A-29(c)).**
> * Three **system-emitted escalation reasons** were added to §5.9 before the P1 freeze:
>   * `queue_overridden_by_rule` (N1 and queue selection);
>   * `pii_masking_failed` (P7);
>   * `critical_category_suspected` (N6).
>
>   They are not model labels, so **no relabeling or retraining is needed, and `taxonomy_version` stays
>   `2026-09-v1`**.
> * **Every reason has a named emitter** (the §5.9 emitter table). `pii_heavy_content` is emitted by N5 and
>   `retention_risk` by N7.
> * **One churn rule everywhere:** high only with explicit cancel intent, a named competitor or an ultimatum; vague
>   "considering alternatives" is medium plus `retention_risk`.
> * **SSO is not a critical category.** An org-wide enterprise `sso_login_failure` raises priority to urgent through
>   the N3 floor.
> * Entities: the model emits `{type, value}` only. The server computes `source_span` in masked-text coordinates.

## Context and Problem Statement

The brief asks for "8–12 ticket intents and 4–6 queues" (brief §11, BR-056). Several categories must be **measured
separately** and **handled specially**:
* critical recall is published for security, widespread outage, cancellation, duplicate charge and payment failure
  (brief §9, BR-044);
* human review is forced for refunds, cancellations, payment disputes, security reports, legal threats, privacy
  requests and active incidents (brief §10, BR-052);
* the demo centres on an SSO failure (brief §12).

Every downstream artifact depends on the label set: training data, the decoding schema, policy rules and lexicons,
routing rules, queues, the UI and the eval metrics. The spec freezes it as `taxonomy_version = "2026-09-v1"`
(§5). Any enum change needs an ADR, a new taxonomy version, relabeling, retraining and a migration.

v1.1 needed new *reasons* for failure paths and gates that had no emitter in v1.0. The question was whether that
counts as a taxonomy change.

Which intent, queue and reason sets does v1 freeze, and how are later additions governed?

## Decision Drivers

* Brief compliance: 8–12 intents, 4–6 queues.
* A separate label for every critical and forced-review category (M-03c, M-07a).
* Learnability at about 3.6k training examples, with explicit disambiguation rules.
* Operational fit: queues map to personas and owners.
* Stability for eval comparability, while still letting *system* reasons evolve without retraining.

## Considered Options

1. 12 intents + reserved `other_unclear`, 6 queues; system-emitted reasons may be added before the P1 freeze without a
   version bump (chosen)
2. 8 intents (merge related categories)
3. 15 intents (finer-grained categories)

## Decision Outcome

Chosen option: option 1. The frozen set (spec §5):

* **Intents:** `sso_login_failure`, `account_access_issue`, `billing_duplicate_charge`, `billing_payment_failure`,
  `refund_request`, `cancellation_request`, `plan_pricing_inquiry`, `service_outage`, `bug_report`,
  `how_to_question`, `security_report`, `privacy_legal_request`. `other_unclear` is a reserved fallback, reported
  separately and not counted in the 12-intent macro-F1.
* **Queues:** `general_support_tier_1`, `technical_support_tier_2`, `billing_and_accounts`,
  `customer_success_retention`, `security_and_privacy`, `incident_response`.
* **Critical categories:** security → `security_report`; widespread outage → `service_outage`; cancellation →
  `cancellation_request`; duplicate charge → `billing_duplicate_charge`; payment failure → `billing_payment_failure`.
  SSO is not critical.
* **Multi-intent:** a primary plus ≤ 2 secondary intents (no duplicates, never the primary; enforced after
  validation). Forced-review rules and N6 use the union.
* **Escalation reasons:** the §5.9 enum, each with a named emitter (P0–P9, N1–N7, or `agent_initiated` from the
  escalation API).

**Governance rule (from the v1.1 note in §5):**

| Change | Handling |
|---|---|
| Model-facing label enum (intents, queues, priorities, sentiments, churn values, entity types, actions) | New taxonomy version, relabel, retrain, migration, registry MAJOR bump |
| System-emitted reason (never produced by the model), before the P1 freeze | ADR amendment only, same taxonomy version |
| System-emitted reason after the freeze | Additive enum migration plus an ADR amendment; the taxonomy version stays unchanged unless model outputs are affected |

### Consequences

* Good, because every brief-required metric and safety rule has a matching label or reason, and every reason is
  traceable to one emitter.
* Good, because failure paths (masking failure, model unavailability, invalid output) and probability gates are
  explicit reasons, visible in the banner, the handoff and the metrics.
* Bad, because more classes mean some structurally confusable pairs (duplicate charge vs refund, SSO vs account
  access, outage vs bug). Mitigations: disambiguation rules, labeling guidelines with 3+3 examples, model ∪ lexicon,
  N6, and hard-set coverage.
* Neutral, because the reason enum can grow without retraining. The governance rule stops that from becoming a
  loophole for model-facing changes.

### Confirmation

* `T-CONTRACT-triage` (BR-006, BR-028): every brief example field is present with identical names and semantics.
* JSON Schema and decoding-schema snapshot tests, plus the TS type-gen diff. Any **model-facing** enum change fails
  unless `taxonomy_version` is bumped in the same PR (proposed assertion).
* `T-TAXONOMY-coverage` (proposed):
  * every intent has a routing rule and default action (§5.8);
  * every critical or forced intent is covered by a P2–P5 rule in the active rule set;
  * every §5.9 reason has an emitter in the engine (matching the emitter table);
  * every queue has an owner persona.
* `T-DATA-strata` (BR-038): ≥ 120 per critical class in test_synth, plus the hard-set strata.
* `taxonomy_version` is recorded in `ModelMeta`, `model_versions` and eval runs. A mismatch between the served model
  and the app taxonomy fails readiness (proposed).

## Pros and Cons of the Options

### 12 intents + `other_unclear`, 6 queues (reasons governed separately)

* Good, because it is brief-compliant, with a label per critical and forced category, and reasons that evolve safely.
* Bad, because there are more classes to learn, with a few confusable pairs.

### 8 intents

* Good, because there is more data per class and the task is easier.
* Bad, because it merges categories the brief requires to be measured separately, which makes critical recall and
  per-category forced review unmeasurable.

### 15 intents

* Good, because routing is finer.
* Bad, because it exceeds the brief's 8–12 range (the brief outranks the spec), and gives sparser classes and lower
  macro-F1.

## More Information

* Spec (private): §5.1–§5.9 (taxonomy, queues, floors incl. the org-wide SSO rule, churn rule, entity spans,
  reasons and emitters, v1.1 note), §6.2, §9.1–§9.3, §9.6 (MAJOR on taxonomy change), §9.8. Change record W-5, A-04,
  A-06, A-17, A-29 (a)(c), W-m12.
* Brief (private): §4, §5, §9, §10, §11. BR-018, BR-044, BR-052, BR-056.
* Research: [synthetic-data-generation](../research/synthetic-data-generation.md) (generation matrix per intent).
* Related ADRs: ADR-0010 (emitters), ADR-0016, ADR-0017 (N6), ADR-0019 (P7 masking reason).
* Revisit when: error analysis on `hard_dev` shows a persistent confusable pair (a new taxonomy version), or
  `other_unclear` clusters reveal coverage gaps.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (system-emitted reasons added before the
  freeze, emitter table, churn rule, SSO not critical; taxonomy version unchanged).
