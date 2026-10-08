---
doc_key: kb_domain_verification
doc_type: help_article
title: "Domain Verification Guide"
product_areas:
  - sso_identity
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

## Overview

Domain verification in Taskmoor proves that your organization owns the email domain used by your workspace members. Verified domains are required before you can enforce SSO login or enable Just-in-Time (JIT) provisioning. Verification also allows Taskmoor to automatically associate new sign-ups with your workspace when they use a verified domain email.

Domain verification is available on the **Business** and **Enterprise** plans.

## Prerequisites

- You must be a **Workspace Owner** in Taskmoor.
- Your workspace must be on the Business or Enterprise plan.
- You must have access to your domain's DNS management console (e.g., your registrar or DNS provider).

## Step 1: Initiate Domain Verification

1. Log in to Taskmoor as a Workspace Owner.
2. Navigate to **Settings > Security > Domains**.
3. Click **Add Domain**.
4. Enter your email domain (e.g., `yourcompany.com`).
5. Click **Generate Verification Record**.

Taskmoor generates a TXT record that you need to add to your domain's DNS configuration. The record looks like:

```
TXT  _taskmoor-verification.yourcompany.com  taskmoor-verify=abc123xyz
```

## Step 2: Add the DNS TXT Record

1. Log in to your domain's DNS management console.
2. Navigate to the DNS records section.
3. Add a new TXT record with the following values:
   - **Host / Name**: `_taskmoor-verification` (some DNS providers require the full subdomain including your domain, e.g., `_taskmoor-verification.yourcompany.com`).
   - **Type**: `TXT`
   - **Value**: The verification string provided by Taskmoor (e.g., `taskmoor-verify=abc123xyz`).
   - **TTL**: Use the default or set to 3600 (1 hour).
4. Save the DNS record.

## Step 3: Verify the Domain

1. Return to Taskmoor at **Settings > Security > Domains**.
2. Click **Verify** next to the domain you added.
3. Taskmoor performs a DNS lookup to confirm the TXT record exists.

DNS propagation can take up to 48 hours, although most changes take effect within 15 minutes to 2 hours. If verification fails, wait and try again.

Once verified, the domain displays a green checkmark in the Domains list.

## Verifying Multiple Domains

You can verify multiple domains if your organization uses more than one email domain. Repeat the steps above for each domain. Each domain requires its own unique TXT record.

## What Verified Domains Enable

### SSO Enforcement

SSO cannot be enforced until at least one domain is verified. Verification ensures that only users from your organization are required to use SSO. Without verification, enforcing SSO could lock out users with email addresses outside your control.

### JIT Provisioning

Just-in-Time provisioning (available on Business and Enterprise) requires domain verification. When JIT is enabled, users from a verified domain who authenticate through your IdP are automatically added to your Taskmoor workspace without a manual invitation.

### Domain Claiming

When domain verification is complete, existing Taskmoor accounts using that email domain can be claimed into your workspace. Claimed users receive a notification and are merged into the workspace on their next login.

## Managing Verified Domains

### Removing a Domain

1. Go to **Settings > Security > Domains**.
2. Click the options menu next to the verified domain.
3. Select **Remove Domain**.
4. Confirm the removal.

Removing a verified domain does not remove users with that email domain from your workspace. However, SSO enforcement and JIT provisioning will no longer apply to that domain.

### Re-verification

If your DNS records change or the verification expires, Taskmoor may request re-verification. You will see a warning in the Domains list. Follow the same steps to add the updated TXT record and verify again.

## Troubleshooting

### Verification fails with "Record not found"

- DNS propagation may not be complete. Wait up to 48 hours and retry.
- Verify the TXT record is added to the correct subdomain (`_taskmoor-verification`).
- Some DNS providers append the root domain automatically. If your domain is `yourcompany.com`, entering `_taskmoor-verification.yourcompany.com` as the host may result in `_taskmoor-verification.yourcompany.com.yourcompany.com`. Enter only `_taskmoor-verification` in this case.
- Use a DNS lookup tool to confirm the record is publicly visible before retrying in Taskmoor.

### "Domain already claimed by another workspace"

Another Taskmoor workspace has already verified this domain. A domain can only be verified by one workspace. Contact Taskmoor support if you believe this is an error or if you need to transfer the domain to a different workspace.

### DNS record is correct but verification still fails

Some DNS providers apply content filters or truncate long TXT values. Ensure the full verification string is present in the record without extra spaces or line breaks. Try wrapping the value in double quotes if your DNS provider supports it.
