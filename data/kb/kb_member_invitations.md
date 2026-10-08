---
doc_key: kb_member_invitations
doc_type: help_article
title: "Inviting Team Members"
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

Inviting team members to your Taskmoor workspace is the first step to collaborative project management. This article covers how to send invitations, manage pending invites, and handle common invitation issues. Member invitations are available on all plans, subject to each plan's seat limits.

## Seat Limits by Plan

Before inviting new members, check your available seats:

| Plan | Maximum Seats |
|---|---|
| Free | 5 |
| Starter | 50 |
| Business | 500 |
| Enterprise | Unlimited |

If your workspace is at capacity, you will see error **BILL_ERR_SEAT_LIMIT** when trying to invite new members. You must remove inactive members, upgrade your plan, or purchase additional seats before new invitations can be sent.

## Sending Invitations

### Inviting Individual Members

1. Go to **Settings > Members**.
2. Click **Invite Members**.
3. Enter one or more email addresses, separated by commas.
4. Select the role for the invited users: **Member** (default), **Limited Member**, **Admin**, or **Workspace Owner**.
5. Optionally select one or more projects to add them to automatically upon acceptance.
6. Click **Send Invitations**.

Each invited user receives an email with a link to join the workspace. The invitation link is valid for **7 days**.

### Bulk Invitations

For larger teams, you can invite members in bulk:

1. Go to **Settings > Members**.
2. Click **Invite Members**.
3. Click **Upload CSV**.
4. Upload a CSV file with the following columns: `email`, `role` (optional, defaults to Member), `projects` (optional, comma-separated project names).
5. Review the parsed list and fix any errors.
6. Click **Send All Invitations**.

Bulk invitations are subject to the same seat limits. If the CSV contains more invitations than available seats, none of the invitations are sent. Reduce the list to fit within your seat capacity.

## Managing Pending Invitations

### Viewing Pending Invitations

1. Go to **Settings > Members**.
2. Click the **Pending** tab.
3. The list shows all outstanding invitations with the invited email, role, date sent, and expiration date.

### Resending an Invitation

If an invitation has expired or the recipient did not receive it:

1. Go to **Settings > Members > Pending**.
2. Find the expired or pending invitation.
3. Click **Resend**.
4. A new invitation email is sent with a fresh 7-day expiration.

### Revoking an Invitation

To cancel a pending invitation before it is accepted:

1. Go to **Settings > Members > Pending**.
2. Find the invitation.
3. Click **Revoke**.
4. Confirm the action.

The invitation link is immediately invalidated. The seat reserved by the pending invitation is released.

## Accepting an Invitation

When a user receives a Taskmoor invitation:

1. Click the **Join Workspace** link in the email.
2. If the user already has a Taskmoor account, they are prompted to log in and the workspace is added to their account.
3. If the user is new to Taskmoor, they are guided through account creation: setting a name, password, and optional profile photo.
4. After joining, the user is directed to the workspace and can begin working in any projects they were pre-assigned to.

## Invitation for SSO Workspaces

On workspaces with SSO enforcement (Business and Enterprise plans):

- Invitations still require an email address, but the invited user authenticates through the IdP instead of setting a password.
- If JIT provisioning is enabled, users from a verified domain are automatically added on their first SSO login without needing an explicit invitation.
- If a user who was invited has not been assigned to the Taskmoor application in the IdP, they will receive error **SAML_ERR_401** when attempting to log in via SSO.

## Troubleshooting

### AUTH_ERR_INVITE_EXPIRED

The invitation link has expired. Invitation links are valid for 7 days. Resend the invitation from **Settings > Members > Pending**.

### BILL_ERR_SEAT_LIMIT

Your workspace has reached its maximum seat count. To invite new members:
- Remove inactive members from **Settings > Members** to free up seats.
- Upgrade to a higher plan with a larger seat limit.
- On Enterprise plans, contact your account representative to adjust seat count.

### Invitation email not received

- Ask the recipient to check their spam or junk folder.
- Verify the email address was entered correctly in the invitation.
- If the recipient's email server has previously bounced Taskmoor emails (error NOTIF_ERR_BOUNCE), contact Taskmoor support to clear the bounce flag for that address.
- Some corporate email filters block automated emails. Ask the recipient's IT team to allowlist emails from Taskmoor's sending domain.

### User accepted but cannot see any projects

After accepting an invitation, the user can see only projects they were pre-assigned to during the invitation process, or projects that are visible to all members. To grant access to additional projects, a Project Admin must add them via the project's **Share** settings.
