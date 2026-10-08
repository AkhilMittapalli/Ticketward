---
doc_key: pd_integration_guide
doc_type: product_doc
title: "Third-Party Integration Setup Guide"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Taskmoor integrates with popular third-party tools for messaging, version control, calendars, file storage, and workflow automation. This guide covers the setup process, available features, and plan requirements for each supported integration.

## Integration Availability by Plan

| Integration | Free | Starter | Business | Enterprise |
|-------------|:----:|:-------:|:--------:|:----------:|
| Slack | Yes | Yes | Yes | Yes |
| Google Calendar | Yes | Yes | Yes | Yes |
| Outlook Calendar | Yes | Yes | Yes | Yes |
| Google Drive | Yes | Yes | Yes | Yes |
| Microsoft Teams | -- | Yes | Yes | Yes |
| GitHub | -- | Yes | Yes | Yes |
| Zapier | -- | Yes | Yes | Yes |
| GitLab | -- | -- | Yes | Yes |
| Salesforce | -- | -- | -- | Yes |

## Slack Integration

Available on all plans. The Slack integration enables task notifications, slash commands, and two-way task updates between Taskmoor and Slack.

### Setup

1. Navigate to **Settings > Integrations > Slack**.
2. Click **Connect to Slack** and authorize the Taskmoor app in your Slack workspace.
3. Select the default Slack channel for notifications.

### Features

- **Task notifications**: Receive Slack messages when tasks are created, assigned, or completed.
- **Slash commands**: Use `/taskmoor create` to create tasks directly from Slack.
- **Channel linking**: Link a Slack channel to a Taskmoor project for targeted notifications.
- **Unfurling**: Taskmoor links pasted in Slack automatically expand to show task details.

### Slash Command Reference

| Command | Description |
|---------|-------------|
| `/taskmoor create [title]` | Create a task in the linked project |
| `/taskmoor status [task_id]` | View task status |
| `/taskmoor assign [task_id] [@user]` | Assign a task |
| `/taskmoor list` | List your assigned tasks |

## Microsoft Teams Integration (Starter+)

### Setup

1. Navigate to **Settings > Integrations > Microsoft Teams**.
2. Click **Connect to Teams** and sign in with your Microsoft 365 account.
3. Authorize the Taskmoor app and select the team.

### Features

- Task notification cards in Teams channels
- Adaptive cards with inline action buttons (mark complete, reassign)
- Tab integration to embed Taskmoor boards in Teams channels

## GitHub Integration (Starter+)

### Setup

1. Navigate to **Settings > Integrations > GitHub**.
2. Click **Connect to GitHub** and authorize the Taskmoor GitHub App.
3. Select the repositories to link.

### Features

- **Branch linking**: Reference a Taskmoor task ID in a branch name (e.g., `feature/task_042-oauth`) to automatically link the branch to the task.
- **PR status sync**: When a linked pull request is merged, the associated task status can be automatically updated.
- **Commit references**: Include `[task_042]` in commit messages to attach commits to task activity.

### API Configuration

Link a GitHub repository to a Taskmoor project via the API:

```bash
curl -X POST https://api.taskmoor.com/v2/integrations/github/repos \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_owner": "your-org",
    "repo_name": "your-repo",
    "project_id": "proj_001",
    "auto_status_update": true,
    "status_on_merge": "completed"
  }'
```

## GitLab Integration (Business+)

### Setup

1. Navigate to **Settings > Integrations > GitLab**.
2. Click **Connect to GitLab** and authorize with your GitLab account.
3. Select the groups and projects to link.

### Features

- Merge request linking to Taskmoor tasks
- Pipeline status reflected on task cards
- Auto-close tasks when linked merge requests are merged

## Google Calendar Integration

Available on all plans. Synchronizes task due dates with Google Calendar.

### Setup

1. Navigate to **Settings > Integrations > Google Calendar**.
2. Click **Connect** and authorize with your Google account.
3. Select which Taskmoor project due dates to sync.

### Behavior

- Tasks with a `due_date` appear as all-day events on the synced calendar.
- Changes to the due date in Taskmoor update the calendar event automatically.
- Deleting the calendar event does not affect the Taskmoor task.

## Outlook Calendar Integration

Available on all plans. Functions identically to Google Calendar integration using the Microsoft Graph API.

## Google Drive Integration

Available on all plans. Attach Google Drive files to tasks and projects.

### Setup

1. Navigate to **Settings > Integrations > Google Drive**.
2. Click **Connect** and authorize file access.
3. Files can now be linked to tasks from the task detail view.

## Zapier Integration (Starter+)

### Setup

1. Log in to Zapier and search for "Taskmoor" in the app directory.
2. Connect your Taskmoor account by providing an API token (`tm_live_` or `tm_test_`).
3. Build Zaps using Taskmoor triggers and actions.

### Available Triggers

| Trigger | Description |
|---------|-------------|
| New Task | Fires when a task is created |
| Task Updated | Fires when a task field changes |
| Task Completed | Fires when a task status changes to completed |
| New Comment | Fires when a comment is added |

### Available Actions

| Action | Description |
|--------|-------------|
| Create Task | Create a new task in a project |
| Update Task | Modify an existing task |
| Add Comment | Post a comment on a task |
| Find Task | Search for a task by title or ID |

## Salesforce Integration (Enterprise)

### Setup

1. Navigate to **Settings > Integrations > Salesforce**.
2. Click **Connect to Salesforce** and authorize using a Salesforce admin account.
3. Configure field mapping between Salesforce objects and Taskmoor tasks.

### Features

- Create Taskmoor tasks from Salesforce records (Opportunities, Cases, or custom objects)
- Sync task status back to Salesforce fields
- Bi-directional updates between linked records

### Field Mapping Configuration

```bash
curl -X POST https://api.taskmoor.com/v2/integrations/salesforce/mappings \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "salesforce_object": "Case",
    "taskmoor_project_id": "proj_001",
    "field_map": {
      "Subject": "title",
      "Description": "description",
      "Priority": "priority",
      "Status": "status"
    },
    "sync_direction": "bidirectional",
    "auto_create": true
  }'
```

## Integration Troubleshooting

### Common Issues

| Issue | Cause | Resolution |
|-------|-------|------------|
| Integration disconnected | OAuth token expired | Reconnect the integration in Settings > Integrations |
| Notifications not delivering | Channel or webhook misconfigured | Verify the notification channel and re-authorize if needed |
| Sync delays | Rate limiting on the third-party service | Taskmoor retries syncs automatically; check third-party service status |
| Permission denied | Insufficient OAuth scopes | Disconnect and reconnect with the required permissions |

### Checking Integration Status

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/integrations"
```

Response:

```json
{
  "data": [
    {
      "id": "int_slack_001",
      "provider": "slack",
      "status": "connected",
      "connected_at": "2026-06-15T08:00:00Z",
      "last_sync_at": "2026-08-01T12:00:00Z"
    },
    {
      "id": "int_github_001",
      "provider": "github",
      "status": "connected",
      "connected_at": "2026-06-20T10:00:00Z",
      "last_sync_at": "2026-08-01T11:55:00Z"
    }
  ]
}
```
