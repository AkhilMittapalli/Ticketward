## Summary

<!-- What changes and why, in two or three sentences. -->

## Linked requirements / decisions

- BR-IDs / PR-IDs: <!-- e.g. BR-027, PR-001 -->
- ADR: <!-- e.g. ADR-0025, or "none" -->
- Phase: <!-- P0..P11 -->

## Type

- [ ] feat
- [ ] fix
- [ ] refactor / chore
- [ ] docs
- [ ] ci / build
- [ ] model / data / eval

## Screenshots

<!-- UI changes only; synthetic data only. -->

## Tests added

<!-- Unit / property / integration / contract / security / e2e. Coverage gate: >= 85%. -->

## Eval impact

<!-- Eval smoke results and metric deltas (M-01..M-13), or "no model/policy/retrieval change". -->

## Security checklist

- [ ] New routes declare an auth dependency (or are added to `PUBLIC_ROUTES` with justification)
- [ ] New routers declare their full `/api/v1/...` prefix
- [ ] Input limits: Pydantic `extra="forbid"` + field bounds; a body limit rule if the route needs more than 64 KB
- [ ] No PII or ticket text in logs, traces or error responses
- [ ] No secrets in code, config, fixtures or docs (gitleaks clean)
- [ ] Errors are RFC 9457 problem+json with safe messages (no exception text)
- [ ] ASVS checklist rows touched by any new route, cookie or external integration are updated
- [ ] Safety rules S-01..S-12 unaffected, or the change is covered by an ADR and tests

## Docs updated

- [ ] README / docs / ADR
- [ ] Knowledge base (Wiki, implementation, current-task, system-status)
- [ ] `docs/research/` re-synced (`make sync-research`) if an ERPROT doc changed
- [ ] `schemas/json` + `docs/openapi.json` regenerated if contracts changed

## Breaking changes

<!-- API, schema, taxonomy (requires a new taxonomy_version) or config changes; "none" otherwise. -->

## Self-review (solo owner; branch protection requires checks, not approvals)

- [ ] PR title follows Conventional Commits (it becomes the squash-merge commit message)
- [ ] I read the full diff, including generated files and lockfiles
- [ ] CI is green, and any skipped check is explained above
