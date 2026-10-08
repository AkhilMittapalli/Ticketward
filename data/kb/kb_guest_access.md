---
doc_key: kb_guest_access
doc_type: help_article
title: "Managing Guest Access"
product_areas:
  - user_admin_permissions
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Guest access in Taskmoor allows you to invite external collaborators -- such as clients, contractors, or partners -- to view and contribute to specific projects without giving them full workspace membership. Guests have limited permissions and do not count toward your seat limit in the same way as full members.

Guest access is available on the **Starter**, **Business**, and **Enterprise** plans.

## Prerequisites

- You must be a **Workspace Owner**, **Admin**, or **Project Admin** to invite guests.
- Your workspace must be on the Starter, Business, or Enterprise plan.
- Guest access must be enabled for your workspace (it is enabled by default).

## Inviting a Guest

1. Open the project you want to share with the guest.
2. Click the **Share** button in the project header.
3. Enter the guest's email address.
4. From the role dropdown, select **Guest**.
5. Optionally add a personal message to the invitation.
6. Click **Send Invitation**.

The guest receives an email invitation with a link to join the project. The invitation link expires after 7 days. If the link expires, the guest sees error **AUTH_ERR_INVITE_EXPIRED** and you need to resend the invitation.

## Guest Permissions

Guests have restricted access compared to full workspace members:

| Capability | Guest | Member |
|---|---|---|
| View assigned projects | Yes | Yes (all) |
| Create and edit tasks | Yes (in assigned projects) | Yes |
| Comment on tasks | Yes | Yes |
| Upload attachments | Yes (subject to plan file limits) | Yes |
| View other projects | No | Yes |
| Access workspace settings | No | No (Admin+ only) |
| Use integrations | No | Yes |
| View dashboards and reports | No | Yes (Starter+) |
| Access the API | No | Yes (Starter+) |

Guests can only see projects they have been explicitly invited to. They cannot browse the workspace project list, view other members' profiles, or access workspace-level features.

## Managing Guests

### Viewing All Guests

1. Go to **Settings > Members**.
2. Click the **Guests** tab.
3. The list shows all guests, the projects they have access to, and when they last logged in.

### Changing Guest Project Access

To add a guest to another project:

1. Open the target project.
2. Click **Share**.
3. Enter the guest's email address (they will appear as an existing guest).
4. Click **Add to Project**.

To remove a guest from a project:

1. Open the project.
2. Click **Share** to view current members and guests.
3. Find the guest and click **Remove from Project**.
4. Confirm the action.

### Converting a Guest to a Full Member

If a guest needs broader workspace access:

1. Go to **Settings > Members > Guests**.
2. Find the guest and click their name.
3. Click **Convert to Member**.
4. Select the appropriate role (Member, Admin, etc.).
5. Click **Confirm**.

The converted user now counts toward your seat limit. If converting a guest would exceed your plan's seat limit, you see error **BILL_ERR_SEAT_LIMIT**. You must add more seats or remove other members first.

### Removing a Guest Entirely

1. Go to **Settings > Members > Guests**.
2. Find the guest and click their name.
3. Click **Remove Guest**.
4. Confirm the action.

Removing a guest revokes their access to all projects. Their previous contributions (tasks, comments) remain in the workspace.

## Guest Limits by Plan

| Plan | Maximum Guests |
|---|---|
| Free | Not available |
| Starter | Up to 10 guests per workspace |
| Business | Up to 100 guests per workspace |
| Enterprise | Unlimited guests |

### File upload limits for guests

Guests share the same file upload limits as regular members based on the workspace plan: 100 MB per file on Starter, 250 MB on Business, and 1 GB on Enterprise.

## Disabling Guest Access

If your organization policy prohibits external access, you can disable guest access entirely:

1. Go to **Settings > Security > Access Controls**.
2. Toggle **Allow Guest Access** to off.
3. Click **Save**.

When guest access is disabled:

- No new guests can be invited.
- Existing guests lose access immediately.
- Their contributions remain in the workspace.
- Re-enabling guest access does not automatically restore previous guest accounts. You must re-invite them.

## Troubleshooting

### AUTH_ERR_INVITE_EXPIRED

The guest's invitation link has expired (valid for 7 days). Resend the invitation from the project's Share dialog or from **Settings > Members > Guests**.

### Guest cannot see tasks in a project

Verify the guest is assigned to the correct project. Guests cannot see tasks in projects they have not been added to. Also check if the tasks are in a section marked as internal-only, which may be hidden from guests.

### BILL_ERR_SEAT_LIMIT when converting a guest

Converting a guest to a full member consumes a seat. If your plan's seat limit is reached (Starter: 50, Business: 500), you must free up a seat or upgrade your plan before the conversion can complete.
