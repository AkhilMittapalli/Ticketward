---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §9.6 (model semver), §12.3 A03:2025, §12.8, §14.4, §14.5; OpenSSF Scorecard checks
informed: contributors (CONTRIBUTING.md, PR template)
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0028: Trunk-based development, Conventional Commits, release-please and SemVer

> **Amended in spec v1.1 (2026-09-27; change record A-26).**
> * **Branch protection requires the status checks but no approvals**, because a solo owner cannot approve their own
>   PRs on GitHub. Review is a documented self-review against the PR checklist. The v1.0 "1 review" wording this ADR
>   flagged is fixed.
> * **Conventional Commits on the PR title.** With squash merges the PR title becomes the commit message, so
>   commitlint checks the PR title in CI.
> * The PR template adds:
>   * the full `/api/v1` router prefix;
>   * ASVS checklist rows touched by any new route, cookie or external integration;
>   * `docs/research/` re-synced if research changed.
> * The CI pipeline gains the `backend-integration`, `compose`, data-gate (`leakage`, `data-provenance`),
>   `asvs-checklist` and `research-sync` jobs. CodeQL covers `actions`.

## Context and Problem Statement

Ticketward is built by one owner, in phases, on a tight schedule (§16). The spec requires:
* trunk-based development on `main`, with short-lived `feat/…`, `fix/…` and `chore/…` branches and squash merges;
* Conventional Commits enforced by commitlint;
* a PR template (BR-IDs/ADR, tests, eval impact, security checklist, docs, self-review);
* SemVer for the app (`v0.x` until DoD, `v1.0.0` at the public demo), with models versioned separately (§9.6);
* release-please for the CHANGELOG and tags;
* a release workflow that builds, signs (cosign) and pushes images to GHCR, with SBOM and eval report attached;
* deploy on tag through a manual-approval environment;
* GitHub Actions pinned by SHA, with minimal `permissions:` per job (§14.4, §14.5).

Which branching, commit and release model fits a solo, security-conscious project, and how is "review" made honest?

## Decision Drivers

* Fast integration with every gate on every PR: lint, tests, contract, eval smoke, data gates, security, ASVS
  completeness, research sync, compose smoke and E2E.
* Automated, trustworthy versioning and changelogs from history.
* Release integrity: signed images, SBOM, pinned actions, least-privilege tokens (A03/A08:2025).
* Low ceremony for one maintainer, without pretending there is a second reviewer.

## Considered Options

1. Trunk-based on `main` + Conventional Commits (PR titles) + release-please + SemVer; required checks, no required
   approvals (chosen)
2. GitFlow (long-lived `develop` and release/hotfix branches)

## Decision Outcome

Chosen option: option 1, because it keeps `main` always releasable and makes versioning mechanical. Required status
checks plus the self-review checklist are the honest equivalent of review for a solo owner.

Rules:

* **Branch protection on `main`:** PR required; status checks required (the §14.5 jobs); conversation resolution;
  CODEOWNERS for sensitive paths (`.github/`, `docs/adr/`, `docs/security/`, `backend/policy/`, `infra/`);
  **0 required approvals** while there is one maintainer, rising to 1 when a second maintainer joins.
* **Commits:** Conventional Commits. commitlint runs on the **PR title** (it becomes the squash commit), and on branch
  commits where useful.
* **Releases:** release-please release PRs, which pass the same checks. The release workflow has minimal permissions
  (`contents: write`, `packages: write`, and `id-token: write` if keyless cosign is used). All third-party actions are
  pinned by commit SHA. Tags are protected. Deploy runs in a manual-approval environment and verifies signatures
  (ADR-0026).
* **Versions:** app SemVer via release-please. Models use `tw-triage-<base>-<method>@MAJOR.MINOR.PATCH`,
  independently (§9.6).

### Consequences

* Good, because there are no long-lived branches, and every change passes the full gate set before landing.
* Good, because releases carry signatures, an SBOM and eval reports. Versions and changelogs come from history.
* Good, because "review" is described honestly (a self-review checklist), not implied by a setting that cannot work
  for a solo owner.
* Bad, because commit-message discipline matters. commitlint on PR titles enforces it.
* Bad, because self-review is weaker than independent review. This is disclosed, with the same insider-risk caveat as
  L-14.

### Confirmation

* Lint stage (§14.5 step 2): commitlint on the PR title.
* Branch protection documented in `DEVELOPER_HANDOFF.md`: required checks = setup/lint, unit + property,
  `backend-integration`, contract, eval-smoke, data gates, security (incl. `asvs-checklist`, `research-sync`), build
  images, `compose`, e2e. CodeQL (`codeql.yml`) covers Python, JS/TS and `actions`.
* `release.yml`: cosign-signed images, CycloneDX SBOM (syft) and the eval report attached. The deploy job verifies the
  signatures.
* OpenSSF Scorecard: Branch-Protection, Code-Review (expected to flag solo self-review, which is disclosed),
  Pinned-Dependencies, Token-Permissions, Dangerous-Workflow, Signed-Releases.

## Pros and Cons of the Options

### Trunk-based + Conventional Commits + release-please + SemVer

* Good, because it is simple, fast and automatable, with an always-green `main`, and honest about solo review.
* Bad, because it needs commit-title discipline, and review strength is limited to self-review.

### GitFlow

* Good, because release and hotfix branches are explicit, which suits multiple supported versions.
* Bad, because long-lived branches cause merge debt, and it is heavy ceremony for a solo, continuously delivered
  project.

## More Information

* Spec (private): §9.6 (model semver), §12.3 (A03/A08:2025), §12.8, §14.1 (`.github/`), §14.4 (branching, PR titles,
  template), §14.5 (CI/CD). Change record A-26.
* Research: no dedicated topic.
* Related ADRs: ADR-0001, ADR-0013, ADR-0026, ADR-0027 (`asvs-checklist` job), ADR-0038 (`research-sync` job).
* Revisit when: a second maintainer joins (turn on required approvals), or several release lines must be supported.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (required checks without approvals, PR
  titles under Conventional Commits, new CI jobs).
