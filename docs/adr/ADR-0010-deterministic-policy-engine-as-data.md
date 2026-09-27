---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §4, §10, §11; spec §5.3, §5.8, §5.9, §7.3, §7.5, §10, §11, §12.4, §13; research prompt-injection-defense, confidence-calibration
informed: ops_lead persona (rule editing), contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0010: Deterministic policy engine as versioned data (YAML → DB)

> **Amended in spec v1.1 (2026-09-27; change record A-05, A-06, A-07, A-09, A-04, W-5).**
> * **All rules are evaluated for every ticket, and every fired rule is recorded** (`rules_fired`: rule id, terminal
>   flag, detector, evidence, reasons). The path comes from the **highest-precedence terminal rule that fired**,
>   stored as `deciding_rule_id`. Evaluation never short-circuits. The v1.0 "first terminal match" wording that this
>   ADR had to clarify is now spec text.
> * **Template precedence, queue selection and P1 composition** are defined tables (§7.3.2). New template
>   `tpl_holding_legal` (P3). P0 restricts the draft to templates only.
> * **New non-terminal rules:**
>   * N5 `pii_heavy_content`: ≥ 8 masked entities, frontier disabled;
>   * N6 `critical_category_suspected`: P(critical) ≥ τ_crit, forces human review, frontier disabled;
>   * N7 `retention_risk`.
> * P7 now covers every pipeline failure (PII masking, model unavailable, schema invalid). P9 is simplified: no
>   evidence or stale-only evidence means `human_escalation` with `tpl_holding_check`, and conflicting evidence (A3)
>   also sits in P9.
> * **Lexicons** add `refund.txt` and `cancellation.txt`. All lexicons run on the NFKC-normalized, invisible-char-
>   stripped **masked** text, and their versions are part of `policy_version`.
> * **Invariants are property tests**, and an import-linter contract keeps `policy` away from providers and chunk
>   text. "First-match evaluation" is recorded as a rejected option.

## Context and Problem Statement

The brief makes safety non-negotiable (brief §4, §10):
* force human review for refunds, cancellations, payment disputes, security reports, legal threats, privacy
  requests and active incidents;
* offer escalation immediately when a customer asks for a person;
* abstain on weak evidence;
* use **"deterministic escalation policies"** (brief §11).

The spec turns this into release-blocking targets: M-07a forced-escalation correctness = **1.00** (published with n
and its exact lower bound), and pooled critical recall ≥ 0.95 at system level.

Ticket text is untrusted (LLM01:2026). The decision must not depend on the model obeying instructions. Ops leads must
edit routing and escalation rules without a deploy, versioned and audited (BR-012, W3).

v1.0 demo case 3 exposed an ambiguity: a duplicate charge with a legal threat fires both P3 and P5. "First terminal
match" would drop P5's reasons, and the handoff must carry every reason (S-10).

How should the path decision (local draft / frontier draft / human escalation / abstain) be made and recorded?

## Decision Drivers

* Guaranteed forced escalation (M-07a = 1.00; S-02, S-03) and recall-first gating on critical categories.
* Injection resistance: the engine never reads model free text, draft text or chunk text.
* Explainability: every fired rule, its evidence and its reasons are recorded, and the deciding rule is explicit.
* Exhaustive, table-driven and property-based testability.
* Ops editability, with versioning, dry run and audit.
* Reproducibility: `policy_version` covers rules, thresholds and lexicon versions.

## Considered Options

1. Deterministic engine as data, **all rules evaluated**, path from the highest terminal rule (chosen)
2. First-match evaluation (stop at the first terminal rule)
3. LLM-as-judge policy
4. OPA/Rego policy-as-code

## Decision Outcome

Chosen option: "deterministic engine as data, with all-rules evaluation", because it is the only option that
*guarantees* M-07a by construction. Forced categories fire on **model ∪ lexicon ∪ incident matcher**, and N6 adds a
probability union. Every reason reaches the handoff, and nothing in ticket text can influence the engine's logic.

Semantics and structure (spec §7.3):

* Rule order: P0 (non-terminal), P1 > P2 > … > P11 (terminal; P11 always fires), N1–N7 (non-terminal).
  `escalation_reasons` is the ordered, deduplicated union of all fired rules' reasons. A rule whose inputs are
  missing records `not_evaluated` with the cause.
* Inputs: enums, calibrated scores, P(critical), lexicon hits on sanitized masked text, retrieval scores, incident
  matches, account metadata. The engine never reads `rationale`, the contents of `churn_signals`, draft text or chunk
  text.
* Tables: queue selection (row 1 P2 → `security_and_privacy`; … row 5 routing after N1), template precedence (P2 ack
  > P3 `tpl_holding_legal` > P4 incident-status > P5 billing/retention > P6/P7 generic > P9 check), and P1
  composition (the offer-a-human sentence is always included).
* Thresholds, fitted on **val only** with the justifying `eval_run_id` (§7.3.1):
  `tau_intent`, `tau_queue`, `tau_ret`, `tau_crit`, `tau_inj`, `tau_entail`, `tau_contra`, `tau_conflict`,
  `pii_heavy_min`.
* `needs_human_review` = human escalation, OR any forced reason (P1–P5), OR N6, OR a confidence gate (P8, N1 low
  confidence).
* Rule-set activation needs the server-side dry run against 60 golden tickets, returns a diff, is audited, and is
  `DEMO_LOCKED` in demo mode (the dry run itself is allowed).
* **Safety floor (proposed; not yet in the spec):** rule-set validation also rejects a set that removes P1–P5,
  makes them non-terminal, or shrinks their lexicons below the shipped versions (threat model AC-17).

### Consequences

* Good, because forced escalation cannot be talked out of. An injection that flips the model label still hits the
  lexicons (P2–P5) and N6, and P0 disables the frontier and model-written drafts.
* Good, because each decision records every fired rule and the deciding rule, so the demo case 3 rendering (P3 path,
  P3 + P5 reasons, `tpl_holding_legal`, billing queue) is reproducible and testable.
* Good, because the engine is cheap (microseconds) and behaves identically in CI, eval and production.
* Bad, because the lexicons and N6 over-escalate (L-11). This is measured as M-07c ≤ 0.15, and τ_crit is raised
  only while val critical recall stays ≥ 0.98.
* Bad, because rule editing is privileged and could weaken safety. Mitigations: Pydantic validation, the golden dry
  run, the proposed safety floor, `rules.activate` audit, RBAC, and `DEMO_LOCKED`.
* Bad, because thresholds come from synthetic val and may not transfer (L-10). The recall-first unions limit the
  damage.

### Confirmation

* Unit tests (table-driven): every rule, all-rules evaluation, recorded reasons, template precedence, queue selection,
  P1 composition, P0 restriction, and every lexicon group (≥ 3 positives/negatives, including benign hard negatives).
  `policy/` ≥ 95% branch coverage.
* Hypothesis properties (§7.3 invariants):
  * a forced-lexicon ticket gives `human_escalation` for any triage output;
  * `final_priority ≥ floor`;
  * the final queue is in the allow-list or is a §7.3.2 forced queue;
  * `frontier_draft` only when every §7.5 condition holds.
* import-linter: `policy` must not import `providers` or retrieval chunk text (§7.1).
* `T-POLICY-forced` with M-07a = 1.00 on eval-smoke (CI gate) and `hard_dev` (P6); golden decisions (path, reasons,
  queue, template) must match (§9.10).
* `T-POLICY-human-request` (M-07d), `T-ROUTE-no-evidence-no-frontier` (S-07), `T-RULES-versioned` (dry run, audit,
  `DEMO_LOCKED`), `T-SEC-RULES-safety-floor` (proposed).
* SLO: forced-escalation correctness 100%; any violation is a Sev-2 incident and postmortem (§15).

## Pros and Cons of the Options

### All-rules deterministic engine (chosen)

* Good, because it is predictable, exhaustive, explainable and injection-proof, and every reason is kept for the
  handoff.
* Bad, because every rule runs on every ticket (negligible cost), and escalation is conservative.

### First-match evaluation

* Good, because it is marginally simpler and cheaper.
* Bad, because it drops the reasons of lower-precedence terminal rules. Demo case 3 would lose the P5 payment-dispute
  and refund reasons, which breaks S-10 handoff completeness and the audit trail.

### LLM-as-judge policy

* Good, because it is flexible with nuance and paraphrase.
* Bad, because it is nondeterministic and injectable (LLM01:2026), cannot guarantee M-07a, adds CPU seconds, and
  contradicts the brief's "deterministic escalation policies".

### OPA/Rego

* Good, because it is standard policy-as-code with its own tooling.
* Bad, because it adds a runtime and a language, and the detectors (lexicons, calibrated scores, incident matcher)
  would still live in Python. It remains possible later behind the same interface.

## More Information

* Spec (private): §5.3 (floors), §5.8 (routing), §5.9 (reasons and emitters), §7.3 (decision table, semantics),
  §7.3.1 (thresholds), §7.3.2 (queue, template, P1 composition), §7.3.3 (lexicons), §7.5, §10 (`policy_rule_sets`,
  `policy_decisions`), §11 (activation), §12.4, §13, §17 (demo case 3). Change record A-04..A-09, W-5.
* Brief (private): §4, §10, §11. BR-021..BR-023, BR-034, BR-052.
* Research: [prompt-injection-defense](../research/prompt-injection-defense.md) (engine as primary control),
  [confidence-calibration](../research/confidence-calibration.md) (τ fitting, N6).
* Related ADRs: ADR-0015 (frontier gate), ADR-0017 (confidence and P(critical)), ADR-0021, ADR-0033, ADR-0034,
  ADR-0035 (`DEMO_LOCKED`).
* Revisit when: M-07c is unacceptable after threshold tuning, or multi-tenant rule sets are needed.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (all-rules evaluation, template/queue
  tables, N5–N7, lexicons, property-tested invariants).
