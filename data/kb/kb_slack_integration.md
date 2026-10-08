---
doc_key: kb_slack_integration
doc_type: help_article
title: "Setting Up the Slack Integration"
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
review_due_at: "2026-12-12"
effective_from: "2026-06-15"
effective_to: null
---

## Overview

The Taskmoor Slack integration allows you to receive task notifications in Slack channels, create tasks from Slack messages, and update task statuses without leaving Slack. The integration is available on all plans.

## Prerequisites

- You must be a **Workspace Admin** in Taskmoor to install the integration.
- You must have permission to install apps in your Slack workspace (or request approval from your Slack admin).

## Installing the Slack Integration

1. In Taskmoor, go to **Workspace Settings > Integrations**.
2. Find **Slack** in the integration list and click **Connect**.
3. You are redirected to Slack's authorization page.
4. Select the Slack workspace you want to connect.
5. Review the permissions Taskmoor requests:
   - Post messages to channels
   - Read messages in channels where the app is added
   - Access user identity for linking accounts
6. Click **Allow**.
7. You are redirected back to Taskmoor with a confirmation message.

## Linking Your Taskmoor and Slack Accounts

After the workspace integration is installed, each team member should link their individual accounts:

1. In Taskmoor, go to **Settings > Integrations > Slack**.
2. Click **Link My Account**.
3. Authorize the connection in the Slack prompt.

Linking accounts enables personalized notifications (e.g., direct messages for tasks assigned to you) and ensures tasks created from Slack are attributed to the correct Taskmoor user.

## Configuring Channel Notifications

### Adding Taskmoor to a Slack Channel

1. In Slack, open the channel where you want Taskmoor notifications.
2. Type `/invite @Taskmoor` or add the Taskmoor app from the channel settings.
3. In Taskmoor, go to **Workspace Settings > Integrations > Slack > Channel Mappings**.
4. Click **+ Add Channel Mapping**.
5. Select the Slack channel and the Taskmoor project to link.
6. Choose which events to post to the channel:

| Event | Description |
|---|---|
| **Task created** | New task added to the project |
| **Task completed** | Task marked as done |
| **Status changed** | Task status updated |
| **Comment added** | New comment on any task |
| **Due date approaching** | Task due within 24 hours |
| **Assignee changed** | Task reassigned |

7. Click **Save**.

Notifications appear in the linked Slack channel as formatted messages with task details and a link to open the task in Taskmoor.

### Multiple Channel Mappings

You can map multiple Taskmoor projects to different Slack channels, or map several projects to the same channel. Each mapping has its own event configuration.

## Creating Tasks from Slack

### Using the Slash Command

Type the following in any Slack channel where the Taskmoor app is installed:

```
/taskmoor create [task title]
```

A modal dialog opens where you can:

- Set the task title (pre-filled from your command).
- Select the target project.
- Set priority, assignee, and due date.
- Add a description.

Click **Create** to add the task to Taskmoor.

### Using Message Actions

To convert a Slack message into a Taskmoor task:

1. Hover over the Slack message.
2. Click the **three-dot menu** (More actions).
3. Select **Create Taskmoor Task**.
4. The message text is pre-filled as the task description.
5. Add a title, select the project, and configure other fields.
6. Click **Create**.

The created task includes a link back to the original Slack message for context.

## Updating Tasks from Slack

When Taskmoor posts a task notification to Slack, the message includes interactive buttons:

- **Change Status**: Select a new status from a dropdown.
- **Assign**: Assign or reassign the task to a team member.
- **Comment**: Post a quick comment on the task.

These actions update the task in Taskmoor in real time.

## Notification Preferences

### Direct Message Notifications

When your accounts are linked, Taskmoor can send you direct messages in Slack for personal events (tasks assigned to you, @-mentions, due date reminders). Configure this in **Settings > Integrations > Slack > Direct Notifications**.

### Muting Channels

If a channel receives too many notifications, you can mute specific event types without removing the channel mapping. Edit the channel mapping in Taskmoor and deselect unwanted event types.

## Troubleshooting

### Notifications Not Appearing in Slack

- Verify the Taskmoor app is added to the Slack channel.
- Check that the channel mapping exists and the correct events are selected.
- Ensure the Slack integration is still authorized in **Workspace Settings > Integrations > Slack**. If the connection shows as "Disconnected," click **Reconnect**.

### Slash Command Not Working

- The `/taskmoor` command is available only in channels where the Taskmoor app is installed.
- If the command returns an error, check that your Taskmoor and Slack accounts are linked.

### SYNC_ERR_CALENDAR

This error code does not apply to the Slack integration. If you see this error, check your calendar sync settings instead.

## Removing the Integration

To disconnect Slack:

1. Go to **Workspace Settings > Integrations > Slack**.
2. Click **Disconnect**.
3. Confirm the removal.

This removes all channel mappings and stops all Slack notifications. Individual account links are also removed. The integration can be reinstalled at any time.

## Related Articles

- Calendar Sync with Google Calendar and Outlook Calendar
- Creating Automation Rules
- Push Notification Settings
