---
# MADR 4.0 front matter. "decision-makers" is MADR 4's name for "Deciders".
status: Proposed          # Proposed | Accepted | Rejected | Deprecated | Superseded by ADR-XXXX
date: YYYY-MM-DD          # date the decision was last updated (not first drafted)
decision-makers: Akhil Mittapalli (owner)
consulted: published research (docs/research/<topic>.md)   # evidence sources, not people, on a solo project
informed: contributors and reviewers (via docs/adr/README.md)
supersedes: none          # ADR-XXXX when this record replaces an earlier one
amended: none             # e.g. "2026-09-27 (spec v1.1)" when a spec version bump refined the decision
---

# ADR-XXXX: {Short title naming the problem solved and the solution chosen}

<!--
How to use this template
- Copy to docs/adr/ADR-XXXX-kebab-case-title.md (next free 4-digit number), fill every section, and add a row to
  docs/adr/README.md.
- Keep it factual. Anything that depends on a library/model/vendor version that must be re-checked when building is
  marked **verify at build** and names the research note that holds the evidence.
- Links: research notes are linked as ../research/<topic>.md (published from the private ERPROT log by
  scripts/sync_research.py, ADR-0038). The spec, the brief and the change records are private: cite them as plain
  text ("spec §7.3", "brief §8", "change record A-14"), never as links.
- Precedence: owner decisions > brief > spec > ADRs. If an ADR changes a spec decision, the spec is updated in the
  same PR and its version is bumped.
- Amending: when a spec version bump refines an Accepted decision without reversing it, amend in place. Add the
  "Amended in spec vX.Y" note below the title, update the affected sections, set `date:`/`amended:`, and add a
  status-history line. A reversed or replaced decision gets a new ADR that supersedes this one.
- A decision is not "Accepted" until its Confirmation mechanism exists or is scheduled for a named phase.
-->

> **Amended in spec vX.Y (YYYY-MM-DD).** {Only when amended: 2–6 bullets saying what changed and why, with the
> change-record IDs (D-nn, A-nn).}

## Context and Problem Statement

{2–5 short paragraphs. Which forces are at play (brief requirements with BR-IDs, spec sections, constraints such as
the CPU-only demo box, the T4 training GPU, the single-VM deployment, the solo owner)? State the problem, ideally as
a question: "How should we …?"}

## Decision Drivers

* {Driver 1: a quality attribute, requirement (BR-xxx / PR-xxx), metric (M-xx) or constraint}
* {Driver 2}

## Considered Options

1. {Option 1 (the chosen option is listed first)}
2. {Option 2}
3. {Option 3}

## Decision Outcome

Chosen option: "{Option 1}", because {which drivers it satisfies, and which trade-offs are consciously accepted}.

{Pinned parameters or versions. Mark anything that must be re-checked as **verify at build** and name the research
note.}

### Consequences

* Good, because {positive consequence}
* Bad, because {negative consequence}; mitigated by {mitigation}
* Neutral, because {…}

### Confirmation

{How compliance is verified, concretely. Name the enforcing test ID (`T-*`), metric (`M-*`, spec §9.8), CI job or
stage (`ci.yml` / `security.yml` / `eval-nightly.yml` / `release.yml`), lint or Semgrep rule, import-linter
contract, or review step. Label anything not yet listed in the spec as "(proposed)". An ADR without a Confirmation
section cannot be Accepted.}

## Pros and Cons of the Options

### {Option 1}

* Good, because {argument}
* Neutral, because {argument}
* Bad, because {argument}

### {Option 2}

* Good, because {argument}
* Bad, because {argument}

## More Information

* Spec (private): §{x.y}; change record {D-nn / A-nn}
* Brief (private): §{n}; requirements BR-{xxx}
* Research: one link per topic, written as `[topic](../research/<topic>.md)` (or "no dedicated research topic")
* Related ADRs: ADR-{XXXX}
* Security docs: [threat model](../security/threat-model.md), [ASVS L2 checklist](../security/asvs-l2-checklist.md)
* Evidence required to move Proposed → Accepted: {only for Proposed ADRs}
* Revisit when: {the trigger that would reopen this decision}
* Status history: {YYYY-MM-DD Proposed; YYYY-MM-DD Accepted (evidence); YYYY-MM-DD Amended (spec vX.Y)}
