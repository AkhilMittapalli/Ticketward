---
doc_key: kb_two_factor_auth
doc_type: help_article
title: "Setting Up Two-Factor Authentication"
product_areas:
  - user_admin_permissions
plans_applicable:
  - free
  - starter
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

Two-factor authentication (2FA) adds an extra layer of security to your Taskmoor account by requiring a time-based one-time password (TOTP) in addition to your regular password. 2FA is available on all plans and can be enabled by individual users or enforced workspace-wide by a Workspace Owner.

## Prerequisites

- A Taskmoor account with password-based login (2FA does not apply to SSO-only accounts).
- A TOTP authenticator app installed on your mobile device, such as Google Authenticator, Microsoft Authenticator, Authy, or 1Password.

## Enabling 2FA for Your Account

1. Log in to Taskmoor.
2. Click your avatar in the bottom-left corner and select **Account Settings**.
3. Go to the **Security** tab.
4. In the **Two-Factor Authentication** section, click **Enable 2FA**.
5. A QR code is displayed on screen.
6. Open your authenticator app and scan the QR code. If you cannot scan the code, click **Enter setup key manually** and type the alphanumeric key into your authenticator app.
7. Enter the 6-digit code from your authenticator app into the verification field in Taskmoor.
8. Click **Verify and Enable**.
9. Taskmoor displays a set of **recovery codes**. Download or copy these codes and store them in a secure location. Each recovery code can be used once to log in if you lose access to your authenticator device.

## Using 2FA to Log In

1. Enter your email and password on the Taskmoor login page.
2. After successful password entry, you are prompted for a 2FA code.
3. Open your authenticator app and enter the current 6-digit code.
4. Click **Verify**.

Codes refresh every 30 seconds. If a code expires while you are entering it, wait for the next code. If you enter an expired code, you will see error **AUTH_ERR_MFA_TIMEOUT** (code expired). Simply wait for the next code and try again.

## Using Recovery Codes

If you lose access to your authenticator device:

1. On the 2FA prompt, click **Use a recovery code**.
2. Enter one of the recovery codes you saved during setup.
3. Click **Verify**.
4. After logging in, immediately set up a new authenticator device by disabling and re-enabling 2FA (see below).

Each recovery code works only once. If you have used all your recovery codes, you must contact a Workspace Owner or Admin to reset your 2FA.

## Disabling 2FA

1. Log in to Taskmoor (using 2FA if it is currently enabled).
2. Go to **Account Settings > Security**.
3. Click **Disable 2FA**.
4. Enter your current password to confirm.
5. Click **Confirm Disable**.

Your recovery codes are invalidated when 2FA is disabled.

## Enforcing 2FA Workspace-Wide

Workspace Owners can require all members to enable 2FA.

1. Go to **Settings > Security > Authentication**.
2. Toggle **Require 2FA for all members**.
3. Click **Save**.

When enforced:

- Members who have not yet enabled 2FA are prompted to set it up on their next login.
- Members have a 7-day grace period to enable 2FA. After the grace period, they are blocked from accessing the workspace until 2FA is configured.
- Workspace Owners and Admins can monitor 2FA adoption in **Settings > Members** by filtering the **2FA Status** column.

## Admin Reset of a User's 2FA

If a member has lost their authenticator device and all recovery codes:

1. A Workspace Owner or Admin goes to **Settings > Members**.
2. Finds the affected user and clicks their name.
3. Clicks **Reset 2FA**.
4. The user's 2FA is removed and they can log in with just their password.
5. If workspace-wide 2FA enforcement is enabled, the user will be prompted to set up 2FA again on their next login.

## Troubleshooting

### AUTH_ERR_MFA_TIMEOUT -- Code Expired

The TOTP code you entered has expired. TOTP codes are valid for 30 seconds. Make sure you are entering the current code displayed in your authenticator app, not a previous one. If this error persists, check that the clock on your mobile device is accurate. TOTP relies on time synchronization; a clock skew of more than 30 seconds will cause codes to fail.

### Authenticator app shows the wrong code

- Ensure your device clock is set to automatic (sync with network time).
- Verify you are using the correct Taskmoor entry in your authenticator app. If you have multiple Taskmoor accounts, each one has a separate entry.
- If the codes still fail, disable 2FA (using a recovery code if needed) and re-enable it to generate a new shared secret.

### All recovery codes used

Contact a Workspace Owner or Admin to reset your 2FA. After the reset, log in and immediately set up a new authenticator device.
