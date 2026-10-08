---
doc_key: kb_saml_setup_google
doc_type: help_article
title: "Configuring SAML SSO with Google Workspace"
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

This guide covers how to set up SAML-based Single Sign-On (SSO) between Google Workspace and Taskmoor. Once configured, users in your Google Workspace organization can log in to Taskmoor with their Google credentials through SAML authentication.

SAML SSO is available on the **Business** and **Enterprise** plans.

## Prerequisites

- You must be a **Workspace Owner** in Taskmoor.
- You must have **Super Admin** privileges in Google Workspace Admin Console.
- Your Taskmoor workspace must be on the Business or Enterprise plan.
- Domain verification should be completed before enforcing SSO.

## Step 1: Gather Taskmoor SSO Details

1. Log in to Taskmoor as a Workspace Owner.
2. Navigate to **Settings > Security > SSO Configuration**.
3. Click **Set Up SAML SSO**.
4. Copy the following values:
   - **ACS URL**
   - **Entity ID**
   - **Start URL** (optional, for IdP-initiated login)

## Step 2: Add a Custom SAML App in Google Workspace

1. Sign in to the Google Admin Console (admin.google.com).
2. Go to **Apps > Web and mobile apps**.
3. Click **Add app > Add custom SAML app**.
4. Enter **Taskmoor** as the app name and optionally upload a logo.
5. Click **Continue**.

## Step 3: Download Google IdP Metadata

On the Google IdP information page:

1. Download the **Certificate** file. This is the IdP signing certificate.
2. Copy the **SSO URL**. This is the Identity Provider Single Sign-On URL.
3. Copy the **Entity ID**. This is the Google IdP Entity ID.
4. Click **Continue**.

## Step 4: Enter Service Provider Details

On the Service Provider Details page in Google Admin Console:

1. **ACS URL**: Paste the ACS URL from Taskmoor.
2. **Entity ID**: Paste the Entity ID from Taskmoor.
3. **Start URL**: Optionally paste the Start URL from Taskmoor for IdP-initiated login.
4. **Name ID Format**: Select **EMAIL**.
5. **Name ID**: Select **Basic Information > Primary email**.
6. Click **Continue**.

### Attribute Mapping

Add the following attribute mappings:

| Google Directory Attribute | App Attribute |
|---|---|
| Primary email | `email` |
| First name | `firstName` |
| Last name | `lastName` |

Click **Finish**.

## Step 5: Enable the App for Users

By default, the new SAML app is turned off for all users.

1. In the Google Admin Console, go to **Apps > Web and mobile apps**.
2. Select the **Taskmoor** app.
3. Click **User access**.
4. To enable for everyone, select **ON for everyone** and click **Save**.
5. To enable for specific organizational units (OUs), select the OU, set the status to **ON**, and click **Save**.

Allow up to 24 hours for changes to propagate across your Google Workspace organization, although it typically takes effect within minutes.

## Step 6: Complete Configuration in Taskmoor

1. Return to the Taskmoor SSO Configuration page.
2. Enter:
   - **IdP SSO URL**: Paste the SSO URL from Google.
   - **IdP Issuer / Entity ID**: Paste the Google Entity ID.
   - **IdP Certificate**: Upload the certificate file downloaded from Google.
3. Click **Save Configuration**.
4. Click **Test Connection** to verify. A successful test opens a new window, authenticates via Google, and returns a confirmation.

## Step 7: Enforce SSO (Optional)

1. In Taskmoor, go to **Settings > Security > SSO Configuration**.
2. Toggle **Enforce SSO for all members**.
3. Confirm.

When enforced, all members must authenticate through Google Workspace. Workspace Owners retain password access as a fallback.

## Troubleshooting

### SAML_ERR_302 -- Signature Invalid

The certificate in Taskmoor does not match the active Google signing certificate. Download the current certificate from the Google Admin Console under the Taskmoor SAML app settings and re-upload it to Taskmoor.

### SAML_ERR_401 -- User Not Assigned

The user's Google Workspace organizational unit does not have the Taskmoor app enabled. Verify the app is turned ON for the user's OU in the Google Admin Console.

### SAML_ERR_415 -- Unsupported NameID

The Name ID Format must be set to **EMAIL** in the Google SAML app configuration. Other formats are not supported by Taskmoor.

### App not appearing in Google App Launcher

After enabling the SAML app, it can take up to 24 hours for the app to appear in users' Google App Launcher tiles. Users can still access Taskmoor via direct URL or SP-initiated login during this period.
