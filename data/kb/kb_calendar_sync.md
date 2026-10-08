---
doc_key: kb_calendar_sync
doc_type: help_article
title: "Syncing Taskmoor with Google Calendar and Outlook Calendar"
product_areas:
  - integrations_api
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

Taskmoor integrates with Google Calendar and Outlook Calendar to sync task due dates as calendar events. This allows you to see your Taskmoor deadlines alongside meetings and other appointments. Calendar sync is available on all plans.

## Supported Calendar Providers

- **Google Calendar** -- Available on all plans via Google Workspace integration.
- **Outlook Calendar** -- Available on all plans via Microsoft 365 integration.

## Setting Up Google Calendar Sync

1. In Taskmoor, go to **Settings > Integrations > Google Calendar**.
2. Click **Connect Google Calendar**.
3. You are redirected to Google's authorization page. Sign in with the Google account associated with the calendar you want to use.
4. Grant Taskmoor permission to:
   - View and edit events on your calendars
   - View your calendar list
5. Click **Allow**.
6. Back in Taskmoor, select the target calendar from the dropdown (e.g., your primary calendar or a dedicated "Taskmoor" calendar).
7. Click **Save**.

### Creating a Dedicated Calendar

For cleaner organization, consider creating a separate Google Calendar for Taskmoor events:

1. In Google Calendar, click the **+** next to "Other calendars" and select **Create New Calendar**.
2. Name it "Taskmoor Tasks" and click **Create**.
3. In Taskmoor's calendar sync settings, select this new calendar as the target.

## Setting Up Outlook Calendar Sync

1. In Taskmoor, go to **Settings > Integrations > Outlook Calendar**.
2. Click **Connect Outlook Calendar**.
3. Sign in with your Microsoft 365 account.
4. Grant Taskmoor permission to access your calendar.
5. Select the target calendar (your default calendar or a specific one).
6. Click **Save**.

## What Gets Synced

### Taskmoor to Calendar (One-Way by Default)

Tasks with due dates are synced to your calendar as all-day events on the due date. The event includes:

- **Event title**: The task title, prefixed with a status indicator (e.g., "[In Progress] Fix login bug").
- **Description**: The task description and a link to open the task in Taskmoor.
- **Color**: Events are color-coded by priority (configurable in sync settings).

### Two-Way Sync (Starter+ Plans)

On Starter, Business, and Enterprise plans, you can enable two-way sync:

1. In **Settings > Integrations > Google Calendar** (or Outlook Calendar), toggle **Two-Way Sync** on.
2. When enabled, moving a calendar event to a different date updates the task's due date in Taskmoor.
3. Deleting a calendar event does not delete the task. It only removes the calendar entry; the task remains in Taskmoor with its due date unchanged.

### Sync Scope

Choose which tasks to sync in the integration settings:

- **All assigned tasks** -- Sync all tasks assigned to you across all projects.
- **Specific projects** -- Sync only tasks from selected projects.
- **Filtered by label** -- Sync only tasks with specific labels.

## Sync Frequency

Calendar sync runs automatically:

- **Real-time push**: When you create, update, or complete a task in Taskmoor, the calendar event is updated within 1-2 minutes.
- **Full sync**: A complete reconciliation runs every 6 hours to catch any discrepancies.
- **Manual sync**: Click **Sync Now** in the integration settings to trigger an immediate full sync.

## Managing Synced Events

### Completed Tasks

When a task is marked complete in Taskmoor, the corresponding calendar event is updated:

- The event title is prefixed with "[Done]".
- By default, completed task events are removed from the calendar after 24 hours. To change this, adjust the **Remove Completed Events** setting to "Immediately," "After 24 hours," "After 7 days," or "Never."

### Recurring Tasks

Recurring tasks create individual calendar events for each occurrence. When the recurrence pattern is updated in Taskmoor, future occurrences are regenerated on the calendar.

## Troubleshooting

### SYNC_ERR_CALENDAR

This error indicates a failure in the sync process. Common causes:

- **Token expired**: Your Google or Microsoft authorization token has expired. Go to the integration settings and click **Reconnect** to reauthorize.
- **Calendar not found**: The target calendar was deleted or its permissions changed. Select a new target calendar.
- **Rate limit**: Too many sync operations in a short period. The system retries automatically after a brief delay.

If SYNC_ERR_CALENDAR persists for more than 24 hours after reconnecting, contact Taskmoor support.

### Events Not Appearing on the Calendar

- Verify the integration status shows "Connected" in **Settings > Integrations**.
- Check that the task has a due date set.
- Confirm the task falls within the sync scope (assigned to you, in a synced project, matching label filters).
- Wait 1-2 minutes for the real-time push to propagate, or click **Sync Now**.

### Duplicate Calendar Events

Duplicates can occur if you disconnect and reconnect the integration without first removing existing synced events. To fix, manually delete the duplicates from your calendar, then run **Sync Now** to regenerate clean events.

## Disconnecting Calendar Sync

1. Go to **Settings > Integrations > Google Calendar** (or Outlook Calendar).
2. Click **Disconnect**.
3. Choose whether to **Keep synced events** on your calendar or **Remove all synced events**.
4. Confirm the disconnection.

You can reconnect at any time. Previously synced events (if kept) are not automatically managed after disconnection.

## Related Articles

- Slack Integration Guide
- Push Notification Settings
- Daily Digest Settings
