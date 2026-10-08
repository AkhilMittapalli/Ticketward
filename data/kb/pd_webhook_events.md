---
doc_key: pd_webhook_events
doc_type: product_doc
title: "Webhook Event Types Catalog"
product_areas:
  - integrations_api
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-18"
effective_from: "2026-07-22"
effective_to: null
---

## Overview

Taskmoor webhooks deliver real-time notifications for events across your workspace. This document catalogs every available webhook event type, its trigger conditions, and the payload structure. Webhooks are available on Business and Enterprise plans and are registered via the `/v2/webhooks` endpoint.

## Event Type Naming Convention

Event types follow the format `{resource}.{action}`:

- `resource`: The Taskmoor entity (e.g., `task`, `project`, `comment`)
- `action`: The operation that occurred (e.g., `created`, `updated`, `deleted`)

## Task Events

### task.created

Triggered when a new task is created in the workspace.

```json
{
  "id": "evt_t001",
  "type": "task.created",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T10:00:00Z",
  "data": {
    "task": {
      "id": "task_100",
      "title": "Implement rate limiter",
      "status": "todo",
      "priority": "high",
      "project_id": "proj_001",
      "assignee_id": "usr_007",
      "created_by": "usr_001",
      "labels": ["backend"],
      "due_date": "2026-08-01",
      "created_at": "2026-07-22T10:00:00Z"
    }
  }
}
```

### task.updated

Triggered when any field on a task is modified. The payload includes `updated_fields` and `previous_values` for changed fields.

```json
{
  "id": "evt_t002",
  "type": "task.updated",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T11:30:00Z",
  "data": {
    "task": {
      "id": "task_100",
      "title": "Implement rate limiter",
      "status": "in_progress",
      "priority": "high",
      "project_id": "proj_001",
      "assignee_id": "usr_007",
      "updated_fields": ["status"],
      "previous_values": {
        "status": "todo"
      },
      "updated_by": "usr_007",
      "updated_at": "2026-07-22T11:30:00Z"
    }
  }
}
```

### task.deleted

Triggered when a task is deleted (moved to trash).

```json
{
  "id": "evt_t003",
  "type": "task.deleted",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T12:00:00Z",
  "data": {
    "task": {
      "id": "task_099",
      "title": "Deprecated feature cleanup",
      "project_id": "proj_001",
      "deleted_by": "usr_001"
    }
  }
}
```

### task.assigned

Triggered when a task's assignee changes.

```json
{
  "id": "evt_t004",
  "type": "task.assigned",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T13:00:00Z",
  "data": {
    "task_id": "task_100",
    "previous_assignee_id": "usr_007",
    "new_assignee_id": "usr_012",
    "assigned_by": "usr_001"
  }
}
```

### task.status_changed

Triggered specifically when a task's status field changes. This is a specialized subset of `task.updated`.

```json
{
  "id": "evt_t005",
  "type": "task.status_changed",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T14:00:00Z",
  "data": {
    "task_id": "task_100",
    "previous_status": "in_progress",
    "new_status": "in_review",
    "changed_by": "usr_007"
  }
}
```

## Project Events

### project.created

```json
{
  "id": "evt_p001",
  "type": "project.created",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T09:00:00Z",
  "data": {
    "project": {
      "id": "proj_012",
      "name": "Q3 Marketing Campaign",
      "owner_id": "usr_005",
      "visibility": "workspace",
      "created_at": "2026-07-22T09:00:00Z"
    }
  }
}
```

### project.updated

Triggered when project metadata changes (name, description, dates, status).

### project.archived

Triggered when a project is archived.

## Comment Events

### comment.created

```json
{
  "id": "evt_c001",
  "type": "comment.created",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T15:00:00Z",
  "data": {
    "comment": {
      "id": "cmt_050",
      "task_id": "task_100",
      "author_id": "usr_012",
      "body_preview": "Reviewed the implementation. Two suggestions...",
      "mention_ids": ["usr_007"],
      "created_at": "2026-07-22T15:00:00Z"
    }
  }
}
```

### comment.deleted

Triggered when a comment is removed.

## Board Events

### board.created

Triggered when a new board is created.

### board.updated

Triggered when board configuration changes (columns added, removed, or reordered).

## User Events

### user.invited

Triggered when a new user is invited to the workspace.

### user.joined

Triggered when an invited user accepts and joins.

### user.deactivated

Triggered when a user is removed or deactivated.

## Webhook Events

### webhook.test

A synthetic event sent when you test a webhook via `POST /v2/webhooks/{id}/test`. Use this to verify your endpoint and signature validation:

```json
{
  "id": "evt_test_001",
  "type": "webhook.test",
  "workspace_id": "ws_001",
  "timestamp": "2026-07-22T16:00:00Z",
  "data": {
    "message": "This is a test delivery from Taskmoor."
  }
}
```

## Complete Event Type List

| Event Type | Description |
|------------|-------------|
| `task.created` | New task created |
| `task.updated` | Task field(s) modified |
| `task.deleted` | Task moved to trash |
| `task.assigned` | Task assignee changed |
| `task.status_changed` | Task status changed |
| `project.created` | New project created |
| `project.updated` | Project metadata changed |
| `project.archived` | Project archived |
| `comment.created` | Comment added to a task |
| `comment.deleted` | Comment removed |
| `board.created` | New board created |
| `board.updated` | Board columns changed |
| `user.invited` | User invited to workspace |
| `user.joined` | User accepted invitation |
| `user.deactivated` | User deactivated |
| `webhook.test` | Test delivery |

## Subscribing to Events

When registering a webhook, specify the event types you want to receive in the `events` array:

```bash
curl -X POST https://api.taskmoor.com/v2/webhooks \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.example.com/hooks/taskmoor",
    "events": ["task.created", "task.updated", "comment.created"],
    "secret": "whsec_your_secret_key"
  }'
```

To subscribe to all events, use the wildcard `"*"` in the events array. Note that new event types added in the future will automatically be delivered to wildcard subscriptions.
