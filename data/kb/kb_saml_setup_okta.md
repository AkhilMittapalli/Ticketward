---
doc_key: kb_saml_setup_okta
doc_type: help_article
title: "Configuring SAML SSO with Okta"
product_areas:
  - sso_identity
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-12"
effective_from: "2026-06-15"
effective_to: null
---

## Overview

This guide walks you through configuring SAML-based Single Sign-On (SSO) between Okta and Taskmoor. Once configured, users assigned to the Taskmoor application in Okta can log in to Taskmoor using their Okta credentials.

SAML SSO is available on the **Business** and **Enterprise** plans.

## Prerequisites

- You must be a **Workspace Owner** in Taskmoor.
- You must have administrator access to your Okta organization.
- Your Taskmoor workspace must be on the Business or Enterprise plan.
- Domain verification must be completed before enabling SSO enforcement. See the domain verification guide for details.

## Step 1: Gather Taskmoor SSO Details

1. Log in to Taskmoor as a Workspace Owner.
2. Navigate to **Settings > Security > SSO Configuration**.
3. Click **Set Up SAML SSO**.
4. Note the following values displayed on the setup page:
   - **ACS URL** (Assertion Consumer Service URL)
   - **Entity ID** (also called Audience URI)
   - **SP Metadata URL** (optional, for automatic configuration)

Keep this page open; you will return to it after configuring Okta.

## Step 2: Create a SAML Application in Okta

1. Log in to the Okta Admin Console.
2. Navigate to **Applications > Applications**.
3. Click **Create App Integration**.
4. Select **SAML 2.0** and click **Next**.
5. Enter **Taskmoor** as the app name. Optionally upload the Taskmoor logo.
6. Click **Next** to proceed to the SAML settings.

## Step 3: Configure SAML Settings in Okta

On the SAML settings page in Okta, enter the following:

| Field | Value |
|---|---|
| Single Sign-On URL | Paste the **ACS URL** from Taskmoor |
| Audience URI (SP Entity ID) | Paste the **Entity ID** from Taskmoor |
| Name ID Format | EmailAddress |
| Application Username | Email |

### Attribute Statements

Add the following attribute mappings:

| Name | Value |
|---|---|
| `email` | `user.email` |
| `firstName` | `user.firstName` |
| `lastName` | `user.lastName` |

Click **Next**, then select **I'm an Okta customer adding an internal app** and click **Finish**.

## Step 4: Download the Okta Metadata

1. In the Okta Admin Console, go to the **Sign On** tab of the Taskmoor application.
2. Under **SAML Signing Certificates**, find the active certificate and click **Actions > Download certificate**.
3. Also copy the following values from the **Sign On** tab:
   - **Identity Provider Single Sign-On URL**
   - **Identity Provider Issuer**

## Step 5: Complete Configuration in Taskmoor

1. Return to the Taskmoor SSO Configuration page.
2. Enter the following:
   - **IdP SSO URL**: Paste the Identity Provider Single Sign-On URL from Okta.
   - **IdP Issuer / Entity ID**: Paste the Identity Provider Issuer from Okta.
   - **IdP Certificate**: Upload the certificate file you downloaded from Okta.
3. Click **Save Configuration**.
4. Click **Test Connection** to verify the setup. Taskmoor will open a new browser window and attempt an SSO login. If the test succeeds, you will see a confirmation message.

## Step 6: Assign Users in Okta

1. In Okta, go to the Taskmoor application.
2. Click the **Assignments** tab.
3. Assign individual users or groups who should have access to Taskmoor.

Users not assigned to the application will receive error **SAML_ERR_401** (user not assigned) when attempting to log in via SSO.

## Step 7: Enforce SSO (Optional)

Once you have verified that SSO login works for assigned users:

1. In Taskmoor, go to **Settings > Security > SSO Configuration**.
2. Toggle **Enforce SSO for all members**.
3. Confirm the action.

When enforced, all workspace members must use SSO to log in. Password-based login is disabled except for Workspace Owners, who retain password access as a fallback.

## Troubleshooting

### SAML_ERR_302 -- Signature Invalid

- The signing certificate in Taskmoor does not match the active certificate in Okta. Re-download the certificate from Okta and upload it to Taskmoor.

### SAML_ERR_408 -- Assertion Expired

- The clock on the Okta server or the user's machine may be out of sync. Ensure NTP is enabled. The SAML assertion has a validity window of 5 minutes.

### SAML_ERR_415 -- Unsupported NameID

- Verify that the Name ID Format in Okta is set to **EmailAddress**. Other formats such as Unspecified or Persistent are not supported.

### Users see "You are not assigned to this application"

- Assign the user or their group to the Taskmoor application in Okta. This corresponds to error code SAML_ERR_401.
