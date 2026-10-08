---
doc_key: kb_jit_provisioning
doc_type: help_article
title: "Just-in-Time (JIT) Provisioning"
product_areas:
  - sso_identity
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Just-in-Time (JIT) provisioning automatically creates Taskmoor user accounts when employees authenticate through your identity provider (IdP) for the first time. Instead of manually inviting each team member, JIT provisioning ensures that any user who successfully authenticates via SAML SSO is automatically added to your Taskmoor workspace.

JIT provisioning is available on the **Business** and **Enterprise** plans.

## Prerequisites

- You must be a **Workspace Owner** in Taskmoor.
- SAML SSO must be configured and tested with a supported IdP (Okta, Azure AD, Google Workspace, or another SAML 2.0 provider on Enterprise).
- At least one domain must be verified. See the domain verification guide.
- Your workspace must be on the Business or Enterprise plan.

## How JIT Provisioning Works

1. A user navigates to your Taskmoor workspace login page or initiates login from the IdP.
2. The user authenticates through your IdP via SAML SSO.
3. If the user does not yet have a Taskmoor account, Taskmoor automatically creates one using the attributes from the SAML assertion (email, first name, last name).
4. The user is added to the workspace with the default role assigned in JIT settings.
5. The user lands in Taskmoor, fully authenticated, without needing a separate invitation.

## Enabling JIT Provisioning

1. Log in to Taskmoor as a Workspace Owner.
2. Navigate to **Settings > Security > SSO Configuration**.
3. Scroll to the **Just-in-Time Provisioning** section.
4. Toggle **Enable JIT Provisioning** to on.
5. Configure the following settings:
   - **Default Role**: Choose the role assigned to JIT-provisioned users. Options are Member (default), Limited Member, or Guest. Workspace Owner and Admin roles cannot be set as the JIT default for security reasons.
   - **Default Team**: Optionally select a team that JIT-provisioned users are automatically added to.
   - **Verified Domains Only**: When enabled (recommended), JIT provisioning only applies to users whose email domain matches a verified domain. This prevents unauthorized accounts from being created.
6. Click **Save**.

## JIT vs. SCIM Provisioning

| Feature | JIT Provisioning | SCIM Provisioning |
|---|---|---|
| Plan required | Business+ | Enterprise only |
| Account creation | On first SSO login | Ahead of first login (push-based) |
| Account deactivation | Manual in Taskmoor | Automatic from IdP |
| Attribute sync | At login time only | Continuous (every 20-40 min) |
| Group assignment | Default team only | Maps IdP groups to Taskmoor teams |
| Setup complexity | Low | Moderate |

Enterprise customers can use both JIT and SCIM together. SCIM handles bulk provisioning and deactivation, while JIT catches any users who are assigned in the IdP but were missed by a SCIM sync cycle.

## Managing JIT-Provisioned Users

### Identifying JIT Users

1. Go to **Settings > Members**.
2. JIT-provisioned users display a "JIT" badge next to their name.
3. You can filter the member list by provisioning method (Manual, JIT, SCIM).

### Changing Roles After Provisioning

JIT-provisioned users receive the default role configured in JIT settings. To change a user's role:

1. Go to **Settings > Members**.
2. Find the user and click their name.
3. Change the role to the appropriate level (Limited Member, Member, Admin, or Workspace Owner).
4. Click **Save**.

### Deactivating JIT Users

JIT provisioning does not handle automatic deactivation. When an employee leaves your organization:

1. Remove or deactivate the user in your IdP so they can no longer authenticate.
2. In Taskmoor, go to **Settings > Members**, find the user, and click **Deactivate**.

For automatic deactivation, consider enabling SCIM provisioning on the Enterprise plan.

## Troubleshooting

### New users are not being created on first login

- Verify JIT provisioning is enabled in **Settings > Security > SSO Configuration**.
- Check that the user's email domain matches a verified domain (if "Verified Domains Only" is enabled).
- Ensure the SAML assertion includes the required attributes: email, firstName, and lastName. Missing attributes prevent account creation.
- Confirm the user is assigned to the Taskmoor application in your IdP. Unassigned users receive error SAML_ERR_401 and no account is created.

### BILL_ERR_SEAT_LIMIT -- Seat limit reached

JIT provisioning fails if your workspace has reached its seat limit. On the Business plan, the maximum is 500 seats. Contact your Workspace Owner to add more seats or remove inactive members before new users can be provisioned.

### Users are created but cannot access projects

JIT-provisioned users start with the default role and team. If specific project access is needed, a Workspace Admin must manually assign them to additional projects or teams after their account is created.
