---
doc_key: kb_daily_digest
doc_type: help_article
title: "Configuring Your Daily Digest Email"
product_areas:
  - notifications_email
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

The daily digest is a summary email sent once per day that consolidates activity across your Taskmoor workspace. Instead of receiving individual email notifications for every update, the digest groups changes by project and presents them in a single, scannable message. All plans include daily digest functionality.

## Enabling or Disabling the Daily Digest

### Per-User Settings

1. Click your avatar in the bottom-left corner of the Taskmoor sidebar.
2. Select **Settings** from the menu.
3. Navigate to **Notifications > Email**.
4. Toggle **Daily Digest** on or off.
5. Click **Save Changes**.

When the daily digest is enabled, Taskmoor suppresses individual email notifications for most routine events (task status changes, comments, assignments) and batches them into the digest instead. High-priority notifications such as @-mentions and due-date warnings are still sent immediately regardless of digest settings.

### Choosing Your Delivery Time

By default, the digest is sent at 08:00 in your local timezone. To change the delivery time:

1. Go to **Settings > Notifications > Email**.
2. Under **Digest Schedule**, select your preferred hour from the dropdown.
3. Taskmoor uses the timezone configured in your profile. To update your timezone, go to **Settings > Profile > Regional Settings**.

The digest is generated based on all activity in the 24 hours preceding the scheduled delivery time.

## What the Digest Includes

The daily digest email contains the following sections:

- **Tasks Assigned to You** -- New assignments and reassignments since the last digest.
- **Due Soon** -- Tasks due within the next 48 hours.
- **Overdue Tasks** -- Tasks past their due date that remain open.
- **Comments and Mentions** -- Comment threads you are involved in, grouped by task.
- **Status Changes** -- Tasks that moved between statuses (e.g., "In Progress" to "Review").
- **Completed Tasks** -- Tasks marked as done in projects you are a member of.

Each item in the digest links directly to the relevant task or project in Taskmoor.

## Workspace-Level Digest Defaults (Admin)

Workspace administrators on Starter, Business, and Enterprise plans can set a default digest preference for new members:

1. Go to **Workspace Settings > Notifications**.
2. Under **Default Email Preferences**, set the digest toggle to on or off.
3. New members joining the workspace will inherit this setting, but can override it in their personal preferences.

On the Free plan, digest settings are managed individually by each user.

## Troubleshooting

### Digest Email Not Arriving

- **Check your spam or junk folder.** Taskmoor sends digests from `notifications@mail.taskmoor.com`. Add this address to your email allow-list.
- **Verify your email address.** Unverified email addresses do not receive digest emails. Go to **Settings > Profile** and confirm your email is verified.
- **Check timezone settings.** If your timezone is incorrect, the digest may arrive at an unexpected hour.
- **NOTIF_ERR_DIGEST error.** If you see this error code in your notification log (visible under **Settings > Notifications > Activity Log** on Starter+ plans), it indicates the digest generation failed for your account. Common causes include a temporarily unreachable email server. The system retries automatically within one hour. If the error persists for more than 24 hours, contact Taskmoor support.

### Digest Contains Stale or Missing Items

The digest captures a snapshot of the previous 24-hour window. If a task was created and then deleted within that window, it will not appear. Similarly, if you were added to a project after the digest generation timestamp, activity from before your addition is not included.

### NOTIF_ERR_BOUNCE

If Taskmoor receives a hard bounce from your email provider, digest delivery is suspended after three consecutive failures. You will see a banner in the Taskmoor web app prompting you to update or re-verify your email address. Once verified, digest delivery resumes with the next scheduled cycle.

## Related Articles

- Push Notification Settings
- Email-to-Task Setup
