---
doc_key: kb_saml_setup_azure_ad
doc_type: help_article
title: "Configuring SAML SSO with Azure AD / Microsoft Entra ID"
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

This guide explains how to configure SAML-based Single Sign-On (SSO) between Azure Active Directory (now Microsoft Entra ID) and Taskmoor. After setup, users assigned to the Taskmoor enterprise application in Azure AD can authenticate using their organizational credentials.

SAML SSO requires the **Business** or **Enterprise** plan.

## Prerequisites

- You must be a **Workspace Owner** in Taskmoor.
- You must have **Global Administrator** or **Application Administrator** permissions in Azure AD (Microsoft Entra ID).
- Your Taskmoor workspace must be on the Business or Enterprise plan.
- Domain verification should be completed before enforcing SSO.

## Step 1: Gather Taskmoor SSO Details

1. Log in to Taskmoor as a Workspace Owner.
2. Go to **Settings > Security > SSO Configuration**.
3. Click **Set Up SAML SSO**.
4. Record the following values:
   - **ACS URL** (Reply URL)
   - **Entity ID** (Identifier)
   - **SP Metadata URL**

## Step 2: Create an Enterprise Application in Azure AD

1. Sign in to the Azure portal (portal.azure.com).
2. Navigate to **Microsoft Entra ID > Enterprise applications**.
3. Click **New application > Create your own application**.
4. Enter **Taskmoor** as the application name.
5. Select **Integrate any other application you don't find in the gallery (Non-gallery)**.
6. Click **Create**.

## Step 3: Configure SAML-Based Sign-On

1. In the Taskmoor enterprise application, go to **Single sign-on** in the left menu.
2. Select **SAML** as the single sign-on method.
3. Under **Basic SAML Configuration**, click **Edit** and enter:
   - **Identifier (Entity ID)**: Paste the Entity ID from Taskmoor.
   - **Reply URL (ACS URL)**: Paste the ACS URL from Taskmoor.
4. Click **Save**.

### Configure Attributes and Claims

1. Under **Attributes & Claims**, click **Edit**.
2. Verify the following claims are present:
   - **Unique User Identifier (Name ID)**: `user.userprincipalname` with format **Email address**. If your UPN does not match users' email addresses, use `user.mail` instead.
   - `email` mapped to `user.mail`
   - `firstName` mapped to `user.givenname`
   - `lastName` mapped to `user.surname`
3. Save the claims configuration.

## Step 4: Download the Azure AD Certificate and Metadata

1. Under **SAML Signing Certificate**, download the **Certificate (Base64)** file.
2. Under **Set up Taskmoor**, copy:
   - **Login URL** (this is the IdP SSO URL)
   - **Azure AD Identifier** (this is the IdP Entity ID / Issuer)

## Step 5: Complete Configuration in Taskmoor

1. Return to the Taskmoor SSO Configuration page.
2. Fill in:
   - **IdP SSO URL**: Paste the Login URL from Azure AD.
   - **IdP Issuer / Entity ID**: Paste the Azure AD Identifier.
   - **IdP Certificate**: Upload the Base64 certificate downloaded from Azure AD.
3. Click **Save Configuration**.
4. Click **Test Connection** to verify. A new browser window opens and attempts SSO login. A success message confirms the configuration is correct.

## Step 6: Assign Users and Groups

1. In Azure AD, go to the Taskmoor enterprise application.
2. Click **Users and groups > Add user/group**.
3. Select the users or Azure AD groups that should have access.
4. Click **Assign**.

Unassigned users who attempt SSO login will receive error **SAML_ERR_401** (user not assigned).

## Step 7: Enforce SSO (Optional)

1. In Taskmoor, navigate to **Settings > Security > SSO Configuration**.
2. Enable **Enforce SSO for all members**.
3. Confirm the change.

Once enforced, password-based login is disabled for all members except Workspace Owners.

## Troubleshooting

### SAML_ERR_302 -- Signature Invalid

The certificate in Taskmoor may not match the active signing certificate in Azure AD. This commonly occurs after Azure AD auto-rotates its signing certificate. Download the current active certificate from Azure AD and re-upload it to Taskmoor.

### SAML_ERR_415 -- Unsupported NameID

Taskmoor requires the NameID format to be `emailAddress`. If the Name ID format is set to Persistent or Unspecified in Azure AD, update the Unique User Identifier claim to use the Email address format.

### SAML_ERR_408 -- Assertion Expired

Verify that both your Azure AD tenant and the user's machine have accurate system clocks. SAML assertions are valid for 5 minutes. Large clock skew causes this error.

### Users receive "AADSTS700016" in Azure AD

This Azure AD error indicates the application identifier does not match. Verify the Entity ID in the Azure AD SAML configuration matches exactly what Taskmoor provides, including protocol and casing.
