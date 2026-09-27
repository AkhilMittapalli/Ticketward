---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §0 knowledge-base convention; MADR 4.0 project documentation
informed: contributors and reviewers (via docs/adr/README.md)
supersedes: none
amended: 2026-09-27 (spec v1.1 alignment; decision unchanged)
---

# ADR-0001: Record architecture decisions in MADR 4 format

> **Amended in spec v1.1 (2026-09-27): alignment only; the decision is unchanged.**
> * Precedence now starts with owner decisions: **owner decisions > brief > spec > ADRs > Wiki > code comments**
>   (spec header; change record D-01..D-06).
> * Spec v1.1 *amends* ADRs in place (§22, "Amended v1.1"). The amendment rule below replaces the old "immutable,
>   supersede only" rule for refinements.
> * Research is now published in the repo (`docs/research/`, ADR-0038), so ADRs link to `../research/<topic>.md`.
>   The spec, brief and change records stay private and are cited as plain text. This resolves the earlier
>   "links resolve only in the owner's workspace" consequence.
> * The ADR set grew to 40 (§22 adds ADR-0031..0040).

## Context and Problem Statement

Ticketward is a production-grade portfolio project with one owner. Hiring reviewers will look at the repo, and future
contributors may join. Both groups need to understand not just *what* was built but *why*: which options were weighed,
which evidence was used, and what trade-offs were accepted.

The spec (`TICKETWARD_SPEC.md` v1.1) sets a strict precedence order:

> owner decisions > brief > spec > ADRs > Wiki > code comments

It also says decisions change "via ADR + version bump", and lists 40 decisions in §22 that need records (DoD-11).
Phase P0 cannot exit until ADR-0001..0010 are merged.

The owner's earlier project (FameWeaver/StorySense) kept rationale in a wiki and in session logs. That rationale was
hard to find, couldn't be diffed during review, and fell out of sync with the code. The spec requires ERPROT research
before every architectural decision (§0). That research needs a durable place where its conclusion is recorded and
linked to the code that enforces it.

How should architectural decisions be recorded so they are reviewable, traceable to requirements and evidence,
enforceable, and cheap enough for one person to keep up?

## Decision Drivers

* Traceability: BR-036 is verified by the "ADR set". DoD-11 needs ADRs for every §22 decision (including the v1.1
  amendments and ADR-0031..0040), plus resolved research documents.
* Governance: decisions change only through an ADR and a spec version bump, so history must be auditable.
* Reviewer legibility: alternatives and trade-offs must be visible, not implied.
* Low overhead for a solo owner: plain Markdown next to the code, reviewed in the same PR.
* Enforceability: each decision says how compliance is checked (test, metric, CI job).
* Separation from volatile docs: the Wiki is "continuous", while decisions need a stable record.

## Considered Options

1. MADR 4 records in `docs/adr/`, one file per decision, with an index and a Confirmation section (chosen)
2. None: rely on the spec and code comments
3. Wiki-only: record decisions as sections of the private Wiki

## Decision Outcome

Chosen option: "MADR 4 records in `docs/adr/`", because it is the only option that gives versioned, reviewable,
per-decision records with alternatives, consequences and a compliance check. It is also the format the spec names in
§22.

Rules adopted:

* **Filenames** are `ADR-NNNN-kebab-case-title.md`. The 4-digit number is never reused (spec W-m6: 4-digit ids
  everywhere). If a title becomes misleading, the file may be renamed in the same PR that updates the index. For
  example ADR-0012 was renamed in v1.1 because it no longer defaults to QLoRA.
* **Statuses**: `Proposed`, `Accepted`, `Rejected`, `Deprecated`, `Superseded by ADR-NNNN`. A record reaches
  `Accepted` only when its Confirmation mechanism exists or is scheduled for a named phase.
* **Amendments**: when a spec version bump *refines* an Accepted decision without reversing it, the ADR is amended in
  place. That means:
  * a dated "Amended in spec vX.Y" note under the title;
  * the affected Context, Decision, Consequences and Confirmation text updated;
  * `date:` and `amended:` set in the front matter;
  * a status-history line.

  A *reversed or replaced* decision gets a new ADR that supersedes the old one. Typo, link and "verify at build"
  evidence updates are allowed in place at any time.
* **Links**: every ADR cites the governing spec sections as plain text ("spec §7.3"), because the spec is private.
  Research is linked as `../research/<topic>.md`. Where the spec has no research topic for a decision, the ADR says
  so. No links into the private knowledge base.
* If an ADR changes a spec decision, the spec is edited and version-bumped **in the same PR**, and owner decisions and
  the brief still win over both.

### Consequences

* Good, because every §22 decision has one findable record showing its options, evidence and enforcement.
* Good, because amendments and supersession give an honest history. A reviewer can see what changed, when, and on
  which owner decision or adjudication.
* Good, because Confirmation sections turn prose into checks (tests, metrics, CI gates), and those checks can be
  audited at DoD time.
* Bad, because 40 records cost time to write and maintain (part of the +12 d production overhead, §16). This is
  mitigated by keeping records concise and focused on decisions, not tutorials.
* Bad, because ADRs and the spec can drift. This is mitigated by the same-PR rule, the v1.1 amendment pass, and the
  proposed index check below.
* Neutral, because in-place amendments make an ADR a living record between version bumps. The status history and the
  change-record IDs keep it auditable.

### Confirmation

* PR template field "Linked BR-IDs/ADR" (§14.4). PRs that change architecture must link an ADR.
* `CODEOWNERS` entry for `docs/adr/` (owner review; self-review checklist, ADR-0028).
* (proposed) A `docs-adr-check` step in the `ci.yml` lint stage that fails when:
  * a file does not match `ADR-\d{4}-[a-z0-9-]+\.md`;
  * front matter lacks `status`, `date` or `decision-makers`;
  * an ADR is missing from the README index, or its status differs from the index;
  * an ADR has no non-empty `### Confirmation` section;
  * an amended ADR lacks its "Amended in spec" note;
  * a `Superseded` ADR names no successor;
  * any ADR links into the private knowledge base, or links a research note whose name is not a published topic.
* DoD-11 release checklist: all §22 decisions have ADRs, and all §23 research topics are resolved and published.

## Pros and Cons of the Options

### MADR 4 in `docs/adr/`

* Good, because it is a widely used, lightweight template (context, drivers, options, outcome, consequences,
  confirmation).
* Good, because the records live with the code, are diffed in PRs and are versioned with releases.
* Good, because MADR 4 has an explicit *Confirmation* section, which fits the spec's "enforceable" culture (§13).
* Neutral, because MADR is a convention, not a tool. The proposed CI check provides the enforcement.
* Bad, because it duplicates some spec text. This is kept small by citing § numbers instead of copying content.

### None (spec and code comments only)

* Good, because it costs nothing up front.
* Bad, because the spec records the *current* decision, but not the rejected alternatives in depth, nor why a
  decision changed between versions.
* Bad, because code comments are last in the precedence order and scattered, so they can't be reviewed as decisions.
* Bad, because it fails DoD-11 and BR-036's "ADR set" verification.

### Wiki-only (private Wiki)

* Good, because it is one place to read and quick to edit.
* Bad, because the Wiki is "continuous" and mutable. Edits overwrite history and are not tied to the PR that
  implements them.
* Bad, because the Wiki is private (D-04 publishes only research), so repo reviewers can't see the rationale.
* Bad, because it is the pattern the spec explicitly moves away from (§0 reference-pattern improvements).

## More Information

* Spec (private): header (precedence and naming), §0 and §0.1 (knowledge-base convention, research publishing),
  §14.4 (PR template), §16 P0 exit criteria, §19 DoD-11, §22 (ADR list with v1.1 amendments). Change record D-04,
  W-m6.
* Brief (private): §8 tech stack (BR-036).
* Research: no dedicated topic. Research notes are linked from each ADR (`../research/`).
* MADR: https://adr.github.io/madr/ (template 4.x). The idea comes from Michael Nygard's "Documenting Architecture
  Decisions" (2011).
* Related ADRs: ADR-0038 (research publishing), ADR-0039 (rename).
* Revisit when: the team grows past one maintainer (add `consulted`/`informed` people and an ADR review cadence), or
  the ADR count makes the index hard to navigate (tag by area).
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 updated for spec v1.1 (precedence, amendment rule,
  research links; decision unchanged).
