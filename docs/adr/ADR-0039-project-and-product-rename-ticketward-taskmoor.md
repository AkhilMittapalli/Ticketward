---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec header (Naming), §3, §12.5, §14, §18, §21 R-18; spec review 2026-09-26 (D-02, D-03)
informed: all contributors; readers of the README, model card and dataset card
supersedes: none
amended: none
---

# ADR-0039: Project and product rename: Ticketward / Taskmoor

## Context and Problem Statement

The brief named the project **ResolveFlow AI** (repo `resolveflow-ai`) and the fictional B2B SaaS **CloudDesk**. The
spec review before the public launch found collisions:
* "ResolveFlow" is used by several near-identical AI support-copilot portfolio repositories on GitHub, by RESOLVEFLOW
  LTD (UK) and by resolveflow.com;
* CloudDesk® is a registered employee-monitoring product, and CloudDesk Software LLC exists.

A public portfolio project (and a fictional company inside it) must not collide with real trademarks or look
derivative of other repositories (R-18).

Which names does the project use, how far does the rename reach (identifiers, cookies, prefixes, registry names), and
what stays unchanged?

## Decision Drivers

* No collision with a real product, company or trademark in any public asset.
* A distinctive name for the public repository, the model and dataset cards, and the demo.
* One consistent identifier scheme (package, env, metrics, roles, cookies, keys), renamed once and mechanically.
* Historical inputs stay unmodified (the brief is immutable).
* Licence-driven naming rules still apply (for example Llama's naming clause).

## Considered Options

1. Rename to **Ticketward** (project) and **Taskmoor** (fictional product), with the identifiers derived from the new
   names and the disclaimer kept (chosen)
2. Keep ResolveFlow AI / CloudDesk

## Decision Outcome

Chosen option: rename (owner decisions D-02, D-03). Neither Ticketward nor Taskmoor had a software product or web
presence on 2026-09-26.

**Names and identifiers:**

| Item | Value |
|---|---|
| Project / repository | Ticketward / `ticketward` |
| Python package / ML package | `ticketward` / `tw_ml` |
| Environment prefix / metrics prefix | `TW_` / `tw_` |
| Database roles | `tw_migrator`, `tw_app`, `tw_readonly`, `tw_purger` |
| Cookies | `__Host-Http-tw_access` (A-30), `__Host-tw_csrf`, `__Secure-tw_refresh` |
| Redis keys | `tw:*` |
| Model registry | `tw-triage-<base>-<method>` (a published Llama-based model must start with "Llama", per its licence; ADR-0011) |
| Service JWT | `iss=tw-svc`, `aud=tw-internal` |
| Fictional product / API-key format | Taskmoor / `tm_live_…`, `tm_test_…` |

**What stays:**
* the brief in the private `reference/` folder keeps its original names and file name (historical, immutable);
* the frozen v1.0 spec keeps its original name in the private archive;
* ADR numbers and file names are unchanged. ADR content was renamed by script.

**Disclaimer:** "Taskmoor is fictional and not affiliated with any real company" appears in the README and the UI
footer.

**README opening:** the brief's sentence, with the new name.

**Re-check:** name availability is re-checked before the public launch (P11, R-18).

### Consequences

* Good, because public assets (repository, HF Hub cards, demo domain) no longer collide with real companies or
  products.
* Good, because one prefix scheme (`tw`, `tm_`) makes secrets scanning and log redaction patterns simple. The research
  publishing scan already blocks `tm_live_`-shaped strings (ADR-0038).
* Bad, because the brief and the implementation use different names, so readers must map them. The spec's Naming note
  and this ADR are the mapping.
* Bad, because a one-off rename touches many files (identifiers, cookies, env names). It was done by a script before
  any release, so no migration of deployed state is needed.
* Neutral, because "Ticketward" is a coined name, and trademark clearance is not a legal opinion. The re-check before
  launch is a best-effort search.

### Confirmation

* The README opening sentence and the Taskmoor disclaimer are present in the README and UI footer (E2E checks the
  footer).
* The cookie names on login, refresh and logout match the table (security suite: cookie names, attributes and
  prefixes).
* A repository search finds no `ResolveFlow`, `CloudDesk`, `resolveflow` or `clouddesk` identifiers outside the
  allowed historical mentions: this ADR, the changelog, and plain-text references to the brief. This is proposed as a
  lint step next to `docs-adr-check`.
* The P11 checklist records the pre-launch availability re-check (R-18).

## Pros and Cons of the Options

### Rename to Ticketward / Taskmoor (chosen)

* Good, because the names are distinctive, collision-free on the check date, and use one consistent identifier
  scheme.
* Bad, because the brief and the code use different names, and there was a one-time rename effort.

### Keep ResolveFlow AI / CloudDesk

* Good, because there is no rename work, and the names match the brief.
* Bad, because of collisions with a registered product (CloudDesk®), an existing company, a domain, and several
  look-alike repositories. That is a legal and reputational risk for a public portfolio.

## More Information

* Spec (private): header (Naming note), §3 (Taskmoor, disclaimer), §12.5 (fictional key format), §14 (repository
  identifiers), §18 (README), §21 R-18. Spec review 2026-09-26: D-02, D-03.
* Research: none (the name checks are recorded in the spec review).
* Related ADRs: ADR-0001 (renames allowed with an index update), ADR-0011 (Llama naming rule), ADR-0020 (cookie
  names), ADR-0038 (public repository).
* Revisit when: the pre-launch re-check finds a collision, or a trademark notice arrives.
* Status history: 2026-09-27 Accepted (new in spec v1.1; owner decisions D-02, D-03).
