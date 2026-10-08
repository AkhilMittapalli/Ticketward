---
doc_key: pd_task_api
doc_type: product_doc
title: "Tasks API Endpoint Reference"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-06"
effective_from: "2026-07-10"
effective_to: null
---

## Overview

The Tasks API provides full CRUD operations for managing tasks within Taskmoor workspaces. Tasks are the primary work unit in Taskmoor and belong to a project. This endpoint is available on Starter, Business, and Enterprise plans.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v2/tasks` | List tasks with filters |
| `POST` | `/v2/tasks` | Create a new task |
| `GET` | `/v2/tasks/{task_id}` | Retrieve a single task |
| `PATCH` | `/v2/tasks/{task_id}` | Update a task |
| `DELETE` | `/v2/tasks/{task_id}` | Delete a task |

## List Tasks

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks?project_id=proj_001&status=in_progress&limit=25"
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `project_id` | string | null | Filter by project |
| `assignee_id` | string | null | Filter by assigned user |
| `status` | string | null | Filter by status: `todo`, `in_progress`, `in_review`, `completed`, `cancelled` |
| `priority` | string | null | Filter by priority: `low`, `medium`, `high`, `urgent` |
| `labels` | string | null | Comma-separated label filter |
| `due_before` | string | null | Tasks due before this ISO 8601 date |
| `due_after` | string | null | Tasks due after this ISO 8601 date |
| `created_after` | string | null | Filter by creation date |
| `updated_after` | string | null | Filter by last update date |
| `search` | string | null | Full-text search on title and description |
| `sort` | string | `created_at` | Sort field: `created_at`, `updated_at`, `due_date`, `priority` |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `limit` | integer | 50 | Results per page (max: 100) |
| `cursor` | string | null | Pagination cursor |

### Response

```json
{
  "data": [
    {
      "id": "task_042",
      "title": "Implement OAuth flow",
      "description": "Add OAuth 2.0 authorization code flow for third-party integrations.",
      "status": "in_progress",
      "priority": "high",
      "project_id": "proj_001",
      "board_id": "board_003",
      "column_id": "col_in_progress",
      "assignee_id": "usr_007",
      "reporter_id": "usr_001",
      "labels": ["backend", "security"],
      "due_date": "2026-07-25",
      "estimated_hours": 16,
      "dependencies": ["task_040"],
      "attachment_count": 2,
      "comment_count": 5,
      "created_at": "2026-07-10T09:00:00Z",
      "updated_at": "2026-07-10T14:30:00Z"
    }
  ],
  "pagination": {
    "cursor": "eyJpZCI6InRhc2tfMDQyIn0=",
    "has_more": true,
    "total_count": 87
  }
}
```

## Create a Task

```bash
curl -X POST https://api.taskmoor.com/v2/tasks \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Set up staging environment",
    "description": "Configure staging server with production-like settings.",
    "project_id": "proj_001",
    "assignee_id": "usr_003",
    "priority": "medium",
    "status": "todo",
    "labels": ["devops", "infrastructure"],
    "due_date": "2026-07-20",
    "estimated_hours": 8
  }'
```

### Create Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `title` | string | Yes | Task title (max 500 characters) |
| `description` | string | No | Markdown-formatted description |
| `project_id` | string | Yes | Parent project ID |
| `assignee_id` | string | No | User ID to assign |
| `priority` | string | No | `low`, `medium`, `high`, `urgent` (default: `medium`) |
| `status` | string | No | Initial status (default: `todo`) |
| `labels` | array | No | Labels to attach |
| `due_date` | string | No | Due date in ISO 8601 format |
| `estimated_hours` | number | No | Estimated effort in hours |
| `parent_task_id` | string | No | Parent task ID for subtasks |
| `dependencies` | array | No | Task IDs this task depends on (Business+) |

## Retrieve a Task

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks/task_042"
```

## Update a Task

```bash
curl -X PATCH https://api.taskmoor.com/v2/tasks/task_042 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_review",
    "assignee_id": "usr_012",
    "labels": ["backend", "security", "reviewed"]
  }'
```

Only fields included in the request body are updated; omitted fields remain unchanged.

## Delete a Task

```bash
curl -X DELETE https://api.taskmoor.com/v2/tasks/task_042 \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content`. Deleted tasks are moved to the workspace trash and can be restored within 30 days by a workspace administrator.

## Task Dependencies (Business+)

Add a dependency between tasks:

```bash
curl -X PATCH https://api.taskmoor.com/v2/tasks/task_045 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "dependencies": ["task_042", "task_043"]
  }'
```

If adding a dependency would create a circular chain, the API returns:

```json
{
  "error": {
    "code": "TASK_ERR_DEP_CYCLE",
    "message": "Adding this dependency would create a cycle: task_045 -> task_042 -> task_045.",
    "details": {
      "cycle": ["task_045", "task_042", "task_045"]
    }
  }
}
```

## File Attachment Limits

File attachments on tasks are subject to per-plan size limits:

| Plan | Max File Size |
|------|:-------------:|
| Free | 10 MB |
| Starter | 100 MB |
| Business | 250 MB |
| Enterprise | 1 GB |
