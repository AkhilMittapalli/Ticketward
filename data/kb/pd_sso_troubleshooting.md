---
doc_key: pd_sso_troubleshooting
doc_type: product_doc
title: "SSO Troubleshooting: Common Errors and Fixes"
product_areas:
  - sso_identity
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-24"
effective_from: "2026-07-28"
effective_to: null
---

## Overview

This guide covers the most common SSO issues encountered by Taskmoor workspace administrators and end users. It provides step-by-step diagnostics and resolution paths for each SAML error code, identity provider configuration issues, and user access problems. SSO is available on Business plans (with supported IdPs) and Enterprise plans (any SAML 2.0 IdP).

## Diagnostic Checklist

Before investigating specific errors, verify the following:

1. **Plan eligibility**: Confirm the workspace is on a Business or Enterprise plan.
2. **SSO enabled**: Check that SAML SSO is toggled on under **Settings > Security > SAML SSO**.
3. **IdP certificate**: Verify the IdP signing certificate uploaded to Taskmoor has not expired.
4. **ACS URL**: Confirm the Assertion Consumer Service URL matches `https://auth.taskmoor.com/saml/acs/{workspace_id}`.
5. **NameID format**: Verify the IdP is configured to send `emailAddress` as the NameID format.
6. **User assignment**: Confirm the user is assigned to the Taskmoor application in the IdP.

## Error: SAML_ERR_302 -- Signature Invalid

**User sees**: "Authentication failed: The SAML response signature could not be verified."

### Diagnosis Steps

1. **Certificate mismatch**: The most common cause. Compare the certificate fingerprint in Taskmoor (**Settings > Security > SAML SSO > IdP Certificate**) with the active signing certificate in your IdP.

2. **Certificate rotation**: Many IdPs rotate signing certificates periodically. If the IdP recently rotated:
   - Download the new certificate from your IdP admin console.
   - Upload it to Taskmoor under **Settings > Security > SAML SSO**.
   - Taskmoor supports dual certificates during rotation: upload the new certificate without removing the old one.

3. **Response modification**: Ensure no proxy, WAF, or load balancer is modifying the SAML response body between the IdP and Taskmoor.

### Quick Fix

```
1. Log in to your IdP admin console.
2. Navigate to the Taskmoor application settings.
3. Download the current signing certificate (PEM or X.509 format).
4. In Taskmoor, go to Settings > Security > SAML SSO.
5. Click "Update IdP Certificate" and upload the downloaded certificate.
6. Ask the affected user to retry login.
```

## Error: SAML_ERR_401 -- User Not Assigned

**User sees**: "You are not authorized to access this Taskmoor workspace."

### Diagnosis Steps

1. **IdP assignment**: Check that the user (or a group the user belongs to) is assigned to the Taskmoor application in your IdP.

   - **Okta**: Applications > Taskmoor > Assignments tab
   - **Azure AD**: Enterprise Applications > Taskmoor > Users and groups
   - **Google Workspace**: Apps > Web and mobile apps > Taskmoor > User access

2. **Workspace invitation**: Even with SSO, users must exist in the Taskmoor workspace. If auto-provisioning is disabled, the user needs a prior invitation.

3. **Email mismatch**: The SAML assertion email must match the email address on the user's Taskmoor account. Check for typos, aliases, or domain differences.

### Resolution

For IdP-side issues:
```
1. Assign the user to the Taskmoor application in your IdP.
2. If using group-based assignment, add the user to the correct group.
3. Wait for the assignment to propagate (typically under 1 minute).
4. Ask the user to retry login.
```

For workspace-side issues:
```
1. In Taskmoor, go to Settings > Members.
2. Invite the user using the same email address configured in the IdP.
3. Once the invitation is accepted, the user can authenticate via SSO.
```

Alternatively, enable **auto-provisioning** under **Settings > Security > SAML SSO > Auto-provision users**. When enabled, users who authenticate through the IdP are automatically added to the workspace as members.

## Error: SAML_ERR_408 -- Assertion Expired

**User sees**: "Authentication failed: The authentication response has expired. Please try again."

### Diagnosis Steps

1. **Clock skew**: The IdP server's system clock may be out of sync with UTC. SAML assertions expire 5 minutes (300 seconds) after the `IssueInstant` timestamp.

2. **Slow redirect**: The user's browser may have taken too long to complete the SAML flow (e.g., pausing on the IdP login page for more than 5 minutes).

3. **Network latency**: High-latency network connections can delay the POST to the ACS URL.

### Resolution

```
1. Verify the IdP server is synchronized via NTP:
   - For on-premises IdPs, check ntpstat or chronyc tracking.
   - Cloud IdPs (Okta, Azure AD) manage clock synchronization automatically.
2. Ask the user to retry login promptly without pausing on the IdP page.
3. If clock skew persists, contact your infrastructure team to correct the IdP server time.
```

## Error: SAML_ERR_415 -- Unsupported NameID Format

**User sees**: "Authentication failed: Unsupported identifier format."

### Diagnosis Steps

The IdP is sending a NameID format other than `emailAddress`. Common incorrect formats:

| Format Sent | Format String |
|-------------|---------------|
| Persistent | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` |
| Unspecified | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` |
| Transient | `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` |

Taskmoor requires: `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`

### Resolution by IdP

**Okta**:
```
1. Applications > Taskmoor > General > SAML Settings > Edit.
2. Set "Name ID format" to "EmailAddress".
3. Set "Application username" to "Email".
4. Save and ask users to retry.
```

**Azure AD**:
```
1. Enterprise Applications > Taskmoor > Single sign-on.
2. Click "Edit" in the User Attributes & Claims section.
3. Set the "Name identifier format" to "Email address".
4. Save the configuration.
```

**Google Workspace**:
```
1. Apps > Web and mobile apps > Taskmoor > SAML attribute mapping.
2. Set the "Name ID" to "Basic Information > Primary email".
3. Set the "Name ID Format" to "EMAIL".
```

## General Troubleshooting Tips

### Enable Debug Mode

Enterprise administrators can enable SAML debug logging under **Settings > Security > SAML SSO > Debug Mode**. This captures the decoded SAML assertion (with sensitive claims redacted) for each login attempt. Debug logs are retained for 7 days.

### Test SSO Without Enforcing

Before enabling **Require SSO** for all workspace members, test the configuration with a small group. Leave password login available as a fallback until SSO is confirmed working.

### Check the Audit Log

Review SSO events in the audit log under **Settings > Security > Audit Log**. Filter by event type `sso.login_failed` to find detailed error context including the raw error code, source IP, and user email.

### Contact Support

If the issue persists after following the steps above, contact Taskmoor support with:

- The `request_id` from the error page (displayed in small text at the bottom)
- The workspace ID
- The IdP name and version
- The SAML debug log (if available)
