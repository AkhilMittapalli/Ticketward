---
doc_key: kb_email_notifications
doc_type: help_article
title: "Configuring Email Notifications"
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
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

## Overview

Taskmoor sends email notifications to keep you informed about task assignments, comments, due dates, and other workspace activity. This article explains how to configure your email notification preferences, manage the daily digest, and troubleshoot common notification issues.

Email notifications are available on all plans.

## Notification Types

Taskmoor sends the following types of email notifications:

### Instant Notifications

Sent immediately (or within a few minutes) when the triggering event occurs:

- **Task assigned**: You are assigned to a task or added as a collaborator.
- **Task mentioned**: Someone mentions you (@mention) in a task description or comment.
- **Comment added**: A new comment is posted on a task you are assigned to or watching.
- **Due date approaching**: A task assigned to you is due within 24 hours.
- **Task completed**: A task you are watching is marked as complete.
- **Task status changed**: A task you are watching changes status.
- **Invitation received**: You receive a workspace or project invitation.

### Daily Digest

A summary email sent once per day (default: 8:00 AM in your timezone) containing:

- Tasks due today.
- Tasks that became overdue since the last digest.
- New comments on tasks you are watching.
- A summary of project activity for projects you belong to.

The daily digest is available on all plans.

## Configuring Notification Preferences

### Individual Notification Settings

1. Click your avatar in the bottom-left corner and select **Account Settings**.
2. Go to the **Notifications** tab.
3. Under **Email Notifications**, toggle each notification type on or off:
   - Task assigned
   - Task mentioned
   - Comment added
   - Due date approaching
   - Task completed
   - Task status changed
4. Click **Save**.

### Daily Digest Settings

1. In **Account Settings > Notifications**, scroll to the **Daily Digest** section.
2. Toggle the daily digest on or off.
3. If enabled, set your preferred delivery time and timezone.
4. Click **Save**.

### Per-Project Notification Settings

You can override workspace-level notification settings for individual projects:

1. Open the project.
2. Click the bell icon in the project header.
3. Choose a notification level:
   - **All activity**: Receive notifications for all events in this project.
   - **Mentions and assignments only**: Only receive notifications when you are directly mentioned or assigned.
   - **None**: Mute all notifications from this project (you still see in-app notifications).
4. The setting applies immediately.

## Watching Tasks

You automatically watch tasks that you created or are assigned to. To watch additional tasks:

1. Open the task.
2. Click the **Watch** button (eye icon) in the task header.
3. You will now receive notifications for comments and status changes on this task.

To stop watching a task, click the eye icon again to unwatch it.

## Email-to-Task (Business and Enterprise)

On the Business and Enterprise plans, you can create tasks by sending an email to your workspace's unique email-to-task address:

1. Go to **Settings > Integrations > Email**.
2. Copy the **Email-to-Task Address** (e.g., `tasks+ws_abc123@inbound.taskmoor.com`).
3. Send an email to this address:
   - **Subject** becomes the task title.
   - **Body** becomes the task description.
   - **Attachments** are added to the task (subject to plan file upload limits).
4. The task is created in the workspace's default project. Reply to the confirmation email to add comments.

## Workspace-Level Notification Policies

Workspace Owners and Admins can set default notification policies:

1. Go to **Settings > Notifications**.
2. Under **Default Notification Policy**, configure which notifications are enabled by default for new members.
3. Members can still override these defaults in their personal settings.

## Troubleshooting

### Emails are not being received

1. **Check spam/junk folder**: Taskmoor emails sometimes get caught by aggressive spam filters. Add Taskmoor's sending domain to your email allowlist.
2. **Verify notification settings**: Go to **Account Settings > Notifications** and confirm the notification types you expect are toggled on.
3. **Check per-project settings**: You may have muted the project. Click the bell icon on the project to verify the notification level.
4. **NOTIF_ERR_BOUNCE**: If Taskmoor has detected that your email address is bouncing (the email server rejects delivery), Taskmoor stops sending emails to that address to protect its sender reputation. Contact Taskmoor support to clear the bounce flag after resolving the underlying email issue.

### Receiving too many notifications

1. **Reduce watched tasks**: Unwatch tasks you no longer need updates on.
2. **Use per-project muting**: Mute projects that generate high volumes of activity but do not require your immediate attention.
3. **Switch to digest-only mode**: Disable all instant notifications and rely on the daily digest for a summary.
4. **Disable specific notification types**: Turn off notification types that are less relevant to your role (e.g., disable "Task completed" if you do not need to track completions).

### NOTIF_ERR_DIGEST -- Digest not delivered

The daily digest email could not be delivered. Common causes:

- The email address on your Taskmoor account is invalid or has a typo.
- The recipient email server temporarily rejected the email (soft bounce). Taskmoor retries digest delivery once. If it fails again, the digest for that day is skipped.
- Verify your email address in **Account Settings** and update it if incorrect.

### Notification delays

Instant notifications are typically delivered within 1-3 minutes of the triggering event. Delays beyond 10 minutes may indicate:

- High email server load on the recipient's side.
- Email throttling by your organization's spam filter.
- Check the Taskmoor status page for any platform-wide notification delays.
