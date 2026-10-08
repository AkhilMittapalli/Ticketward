---
doc_key: pd_project_api
doc_type: product_doc
title: "Projects API Endpoint Reference"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-08"
effective_from: "2026-07-12"
effective_to: null
---

## Overview

The Projects API provides endpoints for managing projects within a Taskmoor workspace. Projects are the top-level organizational container for tasks, boards, and team collaboration. This endpoint is available on Starter, Business, and Enterprise plans.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v2/projects` | List projects in the workspace |
| `POST` | `/v2/projects` | Create a new project |
| `GET` | `/v2/projects/{project_id}` | Retrieve a single project |
| `PATCH` | `/v2/projects/{project_id}` | Update a project |
| `DELETE` | `/v2/projects/{project_id}` | Archive a project |

## List Projects

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/projects?status=active&limit=20"
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `status` | string | null | Filter by status: `active`, `archived`, `completed` |
| `owner_id` | string | null | Filter by project owner |
| `search` | string | null | Full-text search on project name and description |
| `sort` | string | `created_at` | Sort field: `created_at`, `updated_at`, `name` |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `limit` | integer | 50 | Results per page (max: 100) |
| `cursor` | string | null | Pagination cursor |

### Response

```json
{
  "data": [
    {
      "id": "proj_001",
      "name": "Platform Redesign",
      "description": "Complete redesign of the customer-facing platform.",
      "status": "active",
      "owner_id": "usr_001",
      "visibility": "workspace",
      "color": "#4A90D9",
      "task_count": 87,
      "completed_task_count": 34,
      "member_count": 12,
      "boards": [
        {"id": "board_003", "name": "Sprint Board"}
      ],
      "start_date": "2026-06-01",
      "target_date": "2026-09-30",
      "created_at": "2026-06-01T08:00:00Z",
      "updated_at": "2026-07-12T16:45:00Z"
    }
  ],
  "pagination": {
    "cursor": null,
    "has_more": false,
    "total_count": 5
  }
}
```

## Create a Project

```bash
curl -X POST https://api.taskmoor.com/v2/projects \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q3 Marketing Campaign",
    "description": "Plan and execute the Q3 product launch marketing campaign.",
    "owner_id": "usr_005",
    "visibility": "workspace",
    "color": "#7B68EE",
    "start_date": "2026-07-15",
    "target_date": "2026-09-30",
    "template_id": "tmpl_marketing"
  }'
```

### Create Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `name` | string | Yes | Project name (max 200 characters) |
| `description` | string | No | Markdown-formatted project description |
| `owner_id` | string | No | User ID of the project owner (default: API token owner) |
| `visibility` | string | No | `workspace` (visible to all members) or `private` (invited only) |
| `color` | string | No | Hex color code for the project icon |
| `start_date` | string | No | Project start date (ISO 8601 date) |
| `target_date` | string | No | Project target completion date |
| `template_id` | string | No | Template ID to initialize from |

Response:

```json
{
  "id": "proj_012",
  "name": "Q3 Marketing Campaign",
  "description": "Plan and execute the Q3 product launch marketing campaign.",
  "status": "active",
  "owner_id": "usr_005",
  "visibility": "workspace",
  "color": "#7B68EE",
  "task_count": 0,
  "completed_task_count": 0,
  "member_count": 1,
  "boards": [],
  "start_date": "2026-07-15",
  "target_date": "2026-09-30",
  "created_at": "2026-07-12T10:00:00Z",
  "updated_at": "2026-07-12T10:00:00Z"
}
```

## Retrieve a Project

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/projects/proj_001"
```

Returns the full project object including nested board references, member count, and task statistics.

## Update a Project

```bash
curl -X PATCH https://api.taskmoor.com/v2/projects/proj_001 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Platform Redesign v2",
    "target_date": "2026-10-31",
    "description": "Updated scope: includes mobile redesign."
  }'
```

Only fields included in the request body are updated. Omitted fields retain their current values.

## Archive a Project

```bash
curl -X DELETE https://api.taskmoor.com/v2/projects/proj_001 \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content`. Archiving a project hides it from the active project list but retains all data. Archived projects can be restored from **Settings > Projects > Archived**.

To permanently delete a project, an administrator must delete it from the archived list in the Taskmoor web interface. Permanent deletion is not available via the API to prevent accidental data loss.

## Project Members

### List Project Members

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/projects/proj_001/members"
```

Response:

```json
{
  "data": [
    {
      "user_id": "usr_001",
      "role": "owner",
      "joined_at": "2026-06-01T08:00:00Z"
    },
    {
      "user_id": "usr_007",
      "role": "member",
      "joined_at": "2026-06-02T09:30:00Z"
    }
  ]
}
```

### Add a Member

```bash
curl -X POST https://api.taskmoor.com/v2/projects/proj_001/members \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "usr_015",
    "role": "member"
  }'
```

### Member Roles

| Role | Permissions |
|------|-------------|
| `owner` | Full project control, can delete and transfer ownership |
| `admin` | Manage members, configure boards and automations |
| `member` | Create and edit tasks, comment |
| `viewer` | Read-only access to project data |

## Error Responses

| HTTP Status | Description |
|:-----------:|-------------|
| 400 | Malformed request body |
| 401 | Invalid or revoked API token (`API_ERR_401`) |
| 403 | Token lacks required scope or user is not a project member |
| 404 | Project not found or not accessible |
| 422 | Validation error (e.g., missing required `name` field) |
