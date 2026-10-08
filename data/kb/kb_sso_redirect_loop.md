---
doc_key: kb_sso_redirect_loop
doc_type: help_article
title: "Troubleshooting SSO Redirect Loops"
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

A redirect loop during SSO login occurs when the identity provider (IdP) and Taskmoor repeatedly redirect the user's browser without completing authentication. The user typically sees a "too many redirects" error or the browser spins indefinitely between the IdP login page and Taskmoor.

This article covers the most common causes of SSO redirect loops and how to resolve them.

## Prerequisites

- You must be a Workspace Owner or Admin in Taskmoor.
- Your workspace must be on the **Business** or **Enterprise** plan.
- SAML SSO must already be configured with a supported identity provider (Okta, Azure AD, Google Workspace, or another SAML 2.0 provider on Enterprise).

## Common Causes and Solutions

### 1. Incorrect ACS URL Configuration

The Assertion Consumer Service (ACS) URL in your IdP must exactly match the URL provided by Taskmoor.

**Steps to verify:**

1. Navigate to **Settings > Security > SSO Configuration** in Taskmoor.
2. Copy the **ACS URL** displayed on the configuration page.
3. Open your IdP's SAML application settings.
4. Compare the ACS URL in your IdP with the one from Taskmoor. They must match exactly, including the protocol (`https://`) and any trailing slashes.
5. If they differ, update the IdP configuration and save.

### 2. Expired or Invalid SAML Assertion (SAML_ERR_408)

If the clock on your IdP server is out of sync with Taskmoor's servers, the SAML assertion may be considered expired before Taskmoor can process it. This triggers the error code **SAML_ERR_408** (assertion expired).

**Steps to resolve:**

1. Ensure the system clock on your IdP server is synchronized using NTP (Network Time Protocol).
2. Check if the SAML assertion validity window is set too short in your IdP. A minimum of 5 minutes is recommended.
3. If the issue persists, try increasing the clock skew tolerance in your IdP settings.

### 3. Invalid Certificate or Signature (SAML_ERR_302)

An invalid or expired signing certificate causes Taskmoor to reject the SAML response, triggering error code **SAML_ERR_302** (signature invalid). This can create a loop if your IdP retries automatically.

**Steps to resolve:**

1. In Taskmoor, go to **Settings > Security > SSO Configuration**.
2. Download the current IdP certificate stored in Taskmoor.
3. Compare it with the active signing certificate in your IdP. If your IdP has rotated its certificate, you need to upload the new certificate to Taskmoor.
4. Click **Update Certificate**, upload the new certificate file (.pem or .cer), and save.

### 4. Unsupported NameID Format (SAML_ERR_415)

If your IdP sends a NameID format that Taskmoor does not support, the authentication fails with **SAML_ERR_415** (unsupported NameID). Taskmoor requires the NameID format to be `emailAddress`.

**Steps to resolve:**

1. Open your IdP's SAML application configuration.
2. Set the NameID format to `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`.
3. Ensure the NameID value maps to the user's email address attribute.

### 5. User Not Assigned in IdP (SAML_ERR_401)

If the user attempting to log in is not assigned to the Taskmoor application in the IdP, the login fails with **SAML_ERR_401** (user not assigned). Some IdPs redirect back to the login page instead of showing a clear error, which creates a loop.

**Steps to resolve:**

1. In your IdP admin panel, locate the Taskmoor application.
2. Verify that the affected user or their group is assigned to the application.
3. If using group-based assignment, confirm the user belongs to the correct group.

### 6. Browser Cookie or Cache Issues

Stale cookies or cached redirects can cause loops even when the SSO configuration is correct.

**Steps to resolve:**

1. Clear the browser cookies and cache specifically for your Taskmoor workspace URL and your IdP domain.
2. Try logging in using a private or incognito browser window.
3. If the loop resolves in incognito mode, the issue is browser-state related. Clear all cached data for both domains in the regular browser.

## Collecting Diagnostic Information

If the redirect loop persists after checking the steps above, gather the following before contacting Taskmoor support:

- The exact error code displayed (if any), such as SAML_ERR_302, SAML_ERR_401, SAML_ERR_408, or SAML_ERR_415.
- A HAR file capture of the redirect loop from your browser's developer tools.
- The IdP name and version.
- Your Taskmoor workspace URL and region (us, eu, or apac).

Contact Taskmoor support with these details for further investigation.
