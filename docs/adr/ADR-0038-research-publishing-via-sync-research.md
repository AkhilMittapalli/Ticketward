---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §0.1, §12.8, §14.1, §14.4 (PR template), §14.5, §16 P0/P11, §19 DoD-11, §23
informed: readers of docs/research/ and the ADRs; contributors (re-sync when ERPROT changes)
supersedes: none
amended: none
---

# ADR-0038: Public research publishing through `scripts/sync_research.py`

## Context and Problem Statement

Every ADR rests on an Expert Research Protocol (ERPROT) document: primary sources, access dates, findings, and
"unverified" markers. The working copies live in the owner's private knowledge base (`Core files/ERPROT/`), next to
private material:
* the spec and change records;
* session logs and the Wiki;
* local paths, e-mail addresses and notes.

In v1.0, ADR "More information" links pointed into that private folder. In the public repository those links
dangle, and reviewers cannot see the evidence behind the decisions.

The owner decided to publish the research, and only the research (D-04). Copying by hand invites two failures:
* leaking private data (absolute local paths, such as drive-letter home directories, are common in working notes);
* drift between the working copy and the published copy.

How is research published so that ADR links resolve, private data never leaks, and the published copy stays current?

## Decision Drivers

* Evidence behind every decision is public and linkable (`../research/<topic>.md`).
* Fail closed: nothing is published while any private-data finding remains.
* One mechanical path (a script), checked in CI, not a manual procedure.
* Everything else in the private knowledge base stays private: the spec, change records, CLAUDE.md, critical
  directives, session logs, Wiki, plans, status and handoff.

## Considered Options

1. Publish `Core files/ERPROT/` → `docs/research/` through `scripts/sync_research.py` with a private-data scan (chosen)
2. Keep research private
3. Manual copies

## Decision Outcome

Chosen option: the sync script (spec §0.1), because a scripted, fail-closed copy with a privacy scan is the only
option that keeps ADR evidence public without trusting a manual review of every change.

**Spec rules (§0.1):**
* `Core files/ERPROT/` stays the working copy. The published copy is `docs/research/<topic>.md` (same file names).
* The script copies each ERPROT document and handles links: ERPROT-to-ERPROT links stay relative, and spec references
  are plain `§` citations.
* It **fails** (non-zero exit, **no files written**) if any document contains private data:
  * absolute local paths (drive-letter or home-directory);
  * e-mail addresses;
  * secret-like strings;
  * links into `Core files/`.
* It runs whenever an ERPROT document changes and before every release. The PR template asks for a re-sync when
  ERPROT changed.
* ADR research links point to `../research/<topic>.md`. The spec, brief and change records are cited as plain text
  ("spec §7.3"), never linked.

**As built in P0 (`ticketward.tools.publish_research`, wrapper `scripts/sync_research.py`):**
* Modes:
  * publish (default);
  * `--check`: fails if `docs/research/` is stale or has orphaned generated files;
  * `--scan-only`: privacy scan of the published folder, needing no private source;
  * optional `--prune`: deletes orphaned generated notes.
* Exit codes: 0 success; 1 blocked by findings, or stale in `--check`; 2 source folder missing.
* Each published note carries a provenance banner (marker `<!-- published-by: scripts/sync_research.py -->`) stating
  that § references point to the private specification.
* The scan covers:
  * local paths (drive-letter `Users` paths, `/home` and `/Users` paths, OneDrive paths);
  * links that leave the folder (parent-relative or root-relative link targets);
  * `Core files` references;
  * e-mail addresses (reserved example domains excepted);
  * secret patterns (Anthropic, HF, GitHub, AWS and Slack token shapes, PEM private keys, the fictional `tm_live_` /
    `tm_test_` key format).
  * The repository-wide gitleaks job also covers `docs/research/`.
* Links that leave the folder are **rejected rather than rewritten**. This is stricter than the spec's "rewrites
  links", and is reported for a spec update.

**CI:**
* The `research-sync` job (§14.5) runs in the public repository, which does not contain the private working copy. It
  therefore runs the privacy scan (`--scan-only`) on `docs/research/`.
* The staleness check (`--check`) runs where the working copy exists: owner pre-commit and pre-release.
* The spec's wording "CI runs `--check`" is reported for a spec update.

**Audit:** publishing is a repository operation, not an application action. Its evidence is the git history plus the
CI job log. It is **not** an application audit event (see [audit events](../security/audit-events.md)).

### Consequences

* Good, because every ADR's evidence is public and every research link resolves, and the repository becomes
  self-contained for reviewers.
* Good, because private data cannot be published by accident. The scan blocks the whole run, and CI re-scans the
  published folder.
* Good, because drift is caught before each release.
* Bad, because the working notes must be written "publishable": plain § citations, no local paths, no private links.
  The script refuses anything else, which costs some editing time.
* Bad, because a pattern-based scan can miss novel secret formats or personal data. gitleaks in CI and the reserved
  e-mail-domain rule reduce, but do not remove, this risk.
* Neutral, because published notes may cite private spec sections that readers cannot open. The banner says so.

### Confirmation

* Unit tests for `publish_research`:
  * each private pattern blocks publication, and no file is written;
  * reserved e-mail domains pass;
  * the banner is idempotent;
  * `--check` detects stale and orphaned files;
  * exit codes are 0, 1 and 2.
* The `research-sync` CI job is green (privacy scan of `docs/research/`), and gitleaks is green.
* The ADR check (`docs-adr-check`, ADR-0001) finds:
  * no links into `Core files/`;
  * every `../research/<topic>.md` link resolving to a published file;
  * no private-document links.
* DoD-11: every §23 topic is published under `docs/research/` through the script.

## Pros and Cons of the Options

### Sync script with a private-data scan (chosen)

* Good, because it is fail-closed, mechanical, CI-checked, and keeps ADR links working.
* Bad, because notes must follow publishing rules, and the scan is pattern-based.

### Keep research private

* Good, because there is zero leak risk and no tooling.
* Bad, because ADR evidence is invisible, links dangle, and reviewers must take decisions on trust. This is contrary
  to D-04.

### Manual copies

* Good, because there is no code.
* Bad, because copies drift, and a human review of each copy will eventually miss a local path or address. Nothing
  checks it in CI.

## More Information

* Spec (private): §0.1 (research publishing rules), §12.8 (supply-chain and scanning; research publishing), §14.1
  (repository layout), §14.4 (PR template), §14.5 (CI `research-sync` job), §16 P0/P11, §19 DoD-11, §23 (topics).
  Owner decision D-04.
* Research: none. This ADR governs the research folder itself; the index is
  [research README](../research/README.md).
* Related ADRs: ADR-0001 (ADR conventions, link checks), ADR-0028 (CI jobs), ADR-0039 (the public repository name).
* Revisit when: the private knowledge base moves, or a documentation site generator replaces the plain folder.
* Status history: 2026-09-27 Accepted (new in spec v1.1; owner decision D-04).
