---
doc_key: kb_password_reset
doc_type: help_article
title: "Password Reset and Recovery"
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
review_due_at: "2026-12-12"
effective_from: "2026-06-15"
effective_to: null
---

## Overview

This article explains how to reset a forgotten password, change an existing password, and recover access to a locked Taskmoor account. Password-based login is available on all plans. On workspaces with SSO enforcement (Business and Enterprise plans), password login may be restricted to Workspace Owners only.

## Resetting a Forgotten Password

If you have forgotten your Taskmoor password and cannot log in:

1. Go to the Taskmoor login page.
2. Click **Forgot password?** below the password field.
3. Enter the email address associated with your Taskmoor account.
4. Click **Send Reset Link**.
5. Check your email inbox for a message from Taskmoor with the subject "Reset your Taskmoor password."
6. Click the **Reset Password** link in the email.
7. Enter your new password. Passwords must meet the following requirements:
   - Minimum 8 characters.
   - At least one uppercase letter, one lowercase letter, and one number.
   - Cannot be the same as any of your last 5 passwords.
8. Click **Save New Password**.
9. You are redirected to the login page. Log in with your new password.

### Reset link expiration

The password reset link expires after 60 minutes. If the link has expired, return to the login page and request a new reset link.

### Reset email not received

If you do not receive the reset email within 5 minutes:

- Check your spam or junk email folder.
- Verify you entered the correct email address. Taskmoor sends reset emails to the address on file; typos will result in no email being sent.
- If your workspace uses SSO enforcement, password reset is only available for Workspace Owners. Other members must log in via SSO. Contact your Workspace Owner or IT administrator.
- If the error **NOTIF_ERR_BOUNCE** has been recorded for your email address, Taskmoor may have stopped sending emails to your address due to previous bounces. Contact Taskmoor support to clear the bounce flag.

## Changing Your Current Password

If you know your current password and want to change it:

1. Log in to Taskmoor.
2. Click your avatar in the bottom-left corner and select **Account Settings**.
3. Go to the **Security** tab.
4. Click **Change Password**.
5. Enter your current password.
6. Enter your new password (must meet the requirements listed above).
7. Confirm the new password.
8. Click **Update Password**.

A confirmation email is sent to your email address when the password is changed. If you did not initiate the change, click the **Secure your account** link in the email immediately.

## Recovering a Locked Account (AUTH_ERR_LOCKED)

Taskmoor locks an account after 10 consecutive failed login attempts. When locked, the user sees error **AUTH_ERR_LOCKED** and cannot log in even with the correct password.

### Self-service unlock

1. Wait 30 minutes. After the lockout period, the account is automatically unlocked and you can try logging in again.
2. Alternatively, use the **Forgot password?** flow to reset your password. A successful password reset immediately unlocks the account.

### Admin unlock

If a workspace member is locked out and needs immediate access:

1. A Workspace Owner or Admin can go to **Settings > Members**.
2. Find the locked user and click their name.
3. Click **Unlock Account**.
4. The user can now attempt to log in immediately.

## Password Requirements for Workspaces with SSO

On workspaces with SSO enforcement enabled (Business and Enterprise plans):

- **Regular members**: Must log in via SSO. They do not set or manage a Taskmoor password.
- **Workspace Owners**: Retain password-based access as a fallback. Workspace Owners should still set a strong password in case SSO becomes unavailable.
- **Guest users** (Starter+ plans): Log in with their own Taskmoor password unless guest SSO is explicitly configured.

## Two-Factor Authentication and Password Reset

If you have two-factor authentication (2FA) enabled, resetting your password does not disable 2FA. After resetting your password, you will still need to provide your 2FA code on the next login.

If you have lost access to your 2FA device and cannot log in, see the two-factor authentication article for recovery options.

## Troubleshooting

### AUTH_ERR_INVITE_EXPIRED

If you are setting your password for the first time after receiving a workspace invitation and see error **AUTH_ERR_INVITE_EXPIRED**, the invitation link has expired. Invitation links are valid for 7 days. Ask your Workspace Owner or Admin to resend the invitation from **Settings > Members**.

### "Email address not found"

If the password reset page says the email address is not associated with any account, you may be using a different email than the one registered. Try other email addresses you may have used, or contact your Workspace Admin to check which email is on file.
