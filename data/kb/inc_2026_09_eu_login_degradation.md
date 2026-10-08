---
doc_key: inc_2026_09_eu_login_degradation
doc_type: known_incident
title: "EU Region SSO Login Degradation"
product_areas:
  - sso_identity
  - platform_availability
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-10-14"
effective_from: "2026-09-28"
effective_to: null
incident_status: monitoring
started_at: "2026-09-28T08:42:00Z"
resolved_at: null
affected_regions:
  - eu
error_codes:
  - SAML_ERR_302
  - SAML_ERR_408
  - PLAT_ERR_503
last_update_at: "2026-10-01T14:30:00Z"
---

# EU Region SSO Login Degradation

## Summary

Users in the EU region are experiencing intermittent failures when authenticating through SAML-based Single Sign-On (SSO). Affected users encounter `SAML_ERR_302` redirect loops, `SAML_ERR_408` request timeouts, and `PLAT_ERR_503` service unavailable errors when attempting to log in to Taskmoor through their identity provider. The issue affects all plan tiers and is isolated to the EU authentication gateway cluster.

## Impact

- Approximately 12% of EU SSO login attempts are failing intermittently.
- Users authenticating via direct email/password login are not affected.
- No data loss or corruption has been observed.
- EU-based enterprise customers using Okta, Azure AD, and OneLogin as identity providers have all reported failures, confirming the issue is gateway-side rather than IdP-specific.

## Timeline

**2026-09-28 08:42 UTC — Investigating**
Automated monitoring detected a spike in SAML authentication failures in the EU region. The on-call engineering team was paged and began investigation. Initial triage confirmed elevated error rates on the EU authentication gateway (`eu-auth-gw-01` through `eu-auth-gw-04`).

**2026-09-28 10:15 UTC — Identified**
Root cause identified as a certificate rotation issue on the EU authentication gateway cluster. The TLS certificates used for SAML assertion validation were rotated as part of scheduled maintenance on 2026-09-27, but the new intermediate certificate was not propagated to all gateway nodes. Nodes `eu-auth-gw-02` and `eu-auth-gw-03` were still referencing the expired intermediate certificate, causing intermittent SAML validation failures depending on which node handled the request.

**2026-09-29 02:00 UTC — Mitigation Applied**
The correct intermediate certificate was deployed to all EU gateway nodes. Connection pool limits were temporarily increased to handle the backlog of retry attempts. The engineering team also deployed a configuration update to prevent the authentication service from returning `503` errors during certificate validation failures, instead falling back to a queued retry mechanism.

**2026-10-01 14:30 UTC — Monitoring**
Error rates have dropped to baseline levels. The engineering team is maintaining elevated monitoring for an additional observation period to confirm stability. Automated certificate validation checks have been added to the deployment pipeline to prevent recurrence.

## Current Status

The incident is in **monitoring** status. The root cause has been addressed and error rates have returned to normal. The engineering team is observing the system through a full certificate rotation cycle to confirm the fix is durable.

## Workarounds

- Users experiencing SSO login failures can use **direct email/password authentication** as a temporary alternative. Navigate to `app.taskmoor.com/login` and select "Sign in with email" instead of the SSO option.
- Enterprise administrators can temporarily configure a fallback authentication method in **Settings > Security > Authentication** to allow password-based login alongside SSO.
- If a user encounters a `SAML_ERR_302` redirect loop, clearing browser cookies for `*.taskmoor.com` and retrying typically resolves the immediate issue.

## Next Steps

- Complete the 72-hour observation window (expected completion: 2026-10-04).
- Publish post-incident review with permanent remediation plan.
- Roll out automated intermediate certificate propagation verification to all regional gateway clusters.
