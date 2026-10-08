---
doc_key: kb_scim_provisioning
doc_type: help_article
title: "SCIM User Provisioning Setup"
product_areas:
  - sso_identity
plans_applicable:
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

## Overview

SCIM (System for Cross-domain Identity Management) provisioning enables automatic user lifecycle management between your identity provider (IdP) and Taskmoor. When configured, user accounts are automatically created, updated, and deactivated in Taskmoor based on changes in your IdP directory.

SCIM provisioning is available exclusively on the **Enterprise** plan.

## Prerequisites

- You must be a **Workspace Owner** in Taskmoor.
- Your workspace must be on the Enterprise plan.
- SAML SSO must be configured and working before enabling SCIM.
- Your IdP must support SCIM 2.0. Supported providers include Okta, Azure AD (Microsoft Entra ID), Google Workspace, and OneLogin.

## Step 1: Enable SCIM in Taskmoor

1. Log in to Taskmoor as a Workspace Owner.
2. Navigate to **Settings > Security > Provisioning**.
3. Click **Enable SCIM Provisioning**.
4. Taskmoor generates two values:
   - **SCIM Base URL**: The endpoint your IdP will send provisioning requests to.
   - **SCIM Bearer Token**: The authentication token your IdP uses to authorize requests.
5. Copy both values. The bearer token is only shown once. If you lose it, you can regenerate it, but the previous token is immediately invalidated.

## Step 2: Configure SCIM in Your Identity Provider

### Okta

1. In the Okta Admin Console, open the Taskmoor SAML application.
2. Go to the **Provisioning** tab and click **Configure API Integration**.
3. Check **Enable API integration**.
4. Paste the **SCIM Base URL** into the Base URL field.
5. Paste the **SCIM Bearer Token** into the API Token field.
6. Click **Test API Credentials** to verify the connection.
7. Click **Save**.
8. Under **Provisioning > To App**, enable:
   - Create Users
   - Update User Attributes
   - Deactivate Users
9. Save the provisioning settings.

### Azure AD (Microsoft Entra ID)

1. In the Azure portal, go to the Taskmoor enterprise application.
2. Select **Provisioning** in the left menu.
3. Set Provisioning Mode to **Automatic**.
4. Under **Admin Credentials**:
   - **Tenant URL**: Paste the SCIM Base URL.
   - **Secret Token**: Paste the SCIM Bearer Token.
5. Click **Test Connection** to verify.
6. Configure attribute mappings to include email, firstName, lastName, and active status.
7. Set the provisioning scope (all assigned users or sync all users and groups).
8. Click **Save** and then **Start provisioning**.

### OneLogin (Enterprise only)

1. In the OneLogin Admin Console, go to the Taskmoor SAML application.
2. Navigate to **Configuration**.
3. Enter the SCIM Base URL and Bearer Token.
4. Under **Provisioning**, enable user creation, updates, and deactivation.
5. Save the configuration.

## SCIM Attribute Mapping

Taskmoor requires the following SCIM attributes:

| SCIM Attribute | Taskmoor Field | Required |
|---|---|---|
| `userName` | Email address | Yes |
| `name.givenName` | First name | Yes |
| `name.familyName` | Last name | Yes |
| `active` | Account status | Yes |
| `displayName` | Display name | No |

## Managing Provisioned Users

### Automatic Account Creation

When a user is assigned to the Taskmoor application in your IdP, SCIM creates their Taskmoor account automatically. The user receives a welcome email and can log in via SSO immediately.

### User Updates

Changes to user attributes in the IdP (such as name or email) are automatically synchronized to Taskmoor. Synchronization frequency depends on your IdP's provisioning cycle (typically every 20-40 minutes).

### Deactivation

When a user is unassigned from the Taskmoor application or deactivated in the IdP, their Taskmoor account is deactivated. Deactivated users cannot log in but their data (tasks, comments, attachments) is retained.

## Troubleshooting

### SCIM_ERR_409 -- User Already Exists

This error occurs when SCIM attempts to create a user who already has a Taskmoor account with the same email address. To resolve:

1. In Taskmoor, go to **Settings > Members**.
2. Find the existing user and note whether they were manually invited.
3. Either remove the existing account and retry provisioning, or link the existing account by updating the user's SCIM external ID in your IdP.

### SCIM_ERR_422 -- Invalid Attribute

A required attribute is missing or has an invalid format. Verify that:

- The `userName` attribute contains a valid email address.
- `name.givenName` and `name.familyName` are non-empty strings.
- The `active` attribute is a boolean value.

### Provisioning delays

IdP provisioning cycles typically run every 20-40 minutes. If you need immediate provisioning, trigger a manual sync in your IdP's provisioning settings. In Azure AD, this is the **Provision on demand** option. In Okta, use **Push Now** on individual users.

### Token rotation

For security, rotate the SCIM bearer token periodically. In Taskmoor, go to **Settings > Security > Provisioning** and click **Regenerate Token**. Update the new token in your IdP immediately, as the old token is revoked on regeneration.
