---
doc_key: pd_saml_technical
doc_type: product_doc
title: "SAML Technical Configuration and Troubleshooting"
product_areas:
  - sso_identity
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-22"
effective_from: "2026-06-25"
effective_to: null
---

## Overview

Taskmoor supports SAML 2.0 single sign-on for centralized authentication. Business plan customers can configure SSO with supported identity providers, and Enterprise plan customers can use any SAML 2.0-compliant identity provider. This document covers the technical setup, assertion requirements, and troubleshooting steps.

## Supported Identity Providers

| Identity Provider | Plan Required | Configuration |
|-------------------|:-------------:|---------------|
| Okta | Business+ | Pre-built catalog app |
| Azure AD | Business+ | Pre-built gallery app |
| Google Workspace | Business+ | Custom SAML app |
| OneLogin | Enterprise | Pre-built catalog app |
| Other SAML 2.0 | Enterprise | Manual configuration |

## Taskmoor Service Provider Metadata

Configure your identity provider with the following Taskmoor SP values:

| Field | Value |
|-------|-------|
| Entity ID | `https://auth.taskmoor.com/saml/metadata/{workspace_id}` |
| ACS URL | `https://auth.taskmoor.com/saml/acs/{workspace_id}` |
| SLO URL | `https://auth.taskmoor.com/saml/slo/{workspace_id}` |
| NameID Format | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` |
| Signing Algorithm | RSA-SHA256 |
| Binding | HTTP-POST |

Download the full SP metadata XML from **Settings > Security > SAML SSO > Download Metadata**.

## IdP Configuration Requirements

Your identity provider must be configured to send SAML assertions that meet the following requirements:

### Required Attributes

| SAML Attribute | Mapping | Required |
|----------------|---------|:--------:|
| `NameID` | User email address | Yes |
| `firstName` | User's given name | Yes |
| `lastName` | User's family name | Yes |
| `email` | User's email (if NameID is not email) | Conditional |

### Assertion Constraints

- Assertions must be signed using RSA-SHA256.
- Assertions must include an `AudienceRestriction` matching Taskmoor's Entity ID.
- Assertion validity window: 5 minutes (300 seconds) from `IssueInstant`.
- The `NameID` format must be `emailAddress`. Other formats result in `SAML_ERR_415`.

## Step-by-Step Configuration

### 1. Obtain IdP Metadata

Download the SAML metadata XML from your identity provider. This file contains the IdP's Entity ID, SSO URL, SLO URL, and signing certificate.

### 2. Upload IdP Metadata to Taskmoor

Navigate to **Settings > Security > SAML SSO** and click **Configure SAML**. Either upload the metadata XML file or manually enter:

- **IdP Entity ID**: The issuer URI from your IdP
- **IdP SSO URL**: The HTTP-POST binding URL for authentication
- **IdP Certificate**: The X.509 signing certificate (PEM format)

### 3. Test the Configuration

Click **Test SSO Connection** to initiate a test authentication flow. This opens a new browser window and redirects to your IdP for authentication. On success, Taskmoor displays the parsed assertion attributes.

### 4. Enable SSO

After successful testing, toggle **Enable SAML SSO** to activate. Optionally, enable **Require SSO** to enforce SAML authentication for all workspace members (workspace owners retain password login as a fallback).

## Troubleshooting SAML Errors

### SAML_ERR_302 -- Signature Invalid

**Symptom**: Users see "Authentication failed: invalid signature" after IdP redirect.

**Causes and fixes**:
- The IdP signing certificate in Taskmoor does not match the certificate the IdP used to sign the assertion. Re-download and re-upload the IdP certificate.
- The IdP rotated its signing certificate. Update the certificate in Taskmoor SAML settings.
- The assertion was modified in transit. Verify there are no proxies or load balancers rewriting the SAML response body.

### SAML_ERR_401 -- User Not Assigned

**Symptom**: User successfully authenticates at the IdP but receives "You are not authorized to access Taskmoor."

**Causes and fixes**:
- The user is not assigned to the Taskmoor application in the IdP. In Okta, assign the user or group. In Azure AD, ensure the user is in the assigned group.
- The assertion's `NameID` email does not match any invited user in the Taskmoor workspace. Invite the user first, or enable auto-provisioning.

### SAML_ERR_408 -- Assertion Expired

**Symptom**: User sees "Authentication failed: assertion expired."

**Causes and fixes**:
- Clock skew between the IdP and the user's browser exceeds 5 minutes. Synchronize the IdP server's clock using NTP.
- The user's browser took too long to complete the redirect. Ask the user to retry immediately after IdP authentication.

### SAML_ERR_415 -- Unsupported NameID Format

**Symptom**: User sees "Unsupported NameID format."

**Causes and fixes**:
- The IdP is sending a NameID format other than `emailAddress` (commonly `persistent` or `unspecified`). Update the IdP attribute mapping to use `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`.

## SAML Debug Logging

Enterprise customers can enable verbose SAML logging under **Settings > Security > SAML SSO > Debug Mode**. When enabled, Taskmoor logs the raw SAML assertion (redacted of sensitive claims) for each authentication attempt. Debug logs are retained for 7 days and are accessible from the audit log.

## Certificate Rotation

When your IdP rotates its signing certificate, update the certificate in Taskmoor before the old certificate expires. Taskmoor supports uploading a secondary certificate for overlap during rotation. Both certificates are accepted until you remove the old one.
