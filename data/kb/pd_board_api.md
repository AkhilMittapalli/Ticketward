---
doc_key: pd_board_api
doc_type: product_doc
title: "Boards API Endpoint Reference"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-10"
effective_from: "2026-07-14"
effective_to: null
---

## Overview

The Boards API provides endpoints for creating and managing Kanban-style boards within Taskmoor projects. Boards organize tasks into columns that represent workflow stages. This endpoint is available on Starter, Business, and Enterprise plans.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v2/boards` | List boards in the workspace |
| `POST` | `/v2/boards` | Create a new board |
| `GET` | `/v2/boards/{board_id}` | Retrieve a board with columns and tasks |
| `PATCH` | `/v2/boards/{board_id}` | Update board settings |
| `DELETE` | `/v2/boards/{board_id}` | Delete a board |

## List Boards

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/boards?project_id=proj_001"
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `project_id` | string | null | Filter by project |
| `sort` | string | `created_at` | Sort field: `created_at`, `updated_at`, `name` |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `limit` | integer | 50 | Results per page (max: 100) |
| `cursor` | string | null | Pagination cursor |

### Response

```json
{
  "data": [
    {
      "id": "board_003",
      "name": "Sprint Board",
      "project_id": "proj_001",
      "description": "Current sprint workflow tracking.",
      "columns": [
        {"id": "col_backlog", "name": "Backlog", "position": 0, "task_count": 12},
        {"id": "col_todo", "name": "To Do", "position": 1, "task_count": 5},
        {"id": "col_in_progress", "name": "In Progress", "position": 2, "task_count": 8, "wip_limit": 6},
        {"id": "col_review", "name": "Review", "position": 3, "task_count": 3},
        {"id": "col_done", "name": "Done", "position": 4, "task_count": 22}
      ],
      "default_column_id": "col_todo",
      "task_count": 50,
      "created_at": "2026-06-15T08:00:00Z",
      "updated_at": "2026-07-14T11:20:00Z"
    }
  ],
  "pagination": {
    "cursor": null,
    "has_more": false,
    "total_count": 2
  }
}
```

## Create a Board

```bash
curl -X POST https://api.taskmoor.com/v2/boards \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bug Triage Board",
    "project_id": "proj_001",
    "description": "Track and prioritize incoming bug reports.",
    "columns": [
      {"name": "New", "position": 0},
      {"name": "Triaged", "position": 1},
      {"name": "In Progress", "position": 2, "wip_limit": 5},
      {"name": "Fixed", "position": 3},
      {"name": "Verified", "position": 4}
    ],
    "default_column": "New"
  }'
```

### Create Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `name` | string | Yes | Board name (max 200 characters) |
| `project_id` | string | Yes | Parent project ID |
| `description` | string | No | Board description |
| `columns` | array | No | Initial column definitions (default columns are created if omitted) |
| `columns[].name` | string | Yes | Column display name |
| `columns[].position` | integer | Yes | Zero-based column order |
| `columns[].wip_limit` | integer | No | Work-in-progress limit for the column |
| `default_column` | string | No | Name of the column where new tasks are placed |

Response:

```json
{
  "id": "board_007",
  "name": "Bug Triage Board",
  "project_id": "proj_001",
  "description": "Track and prioritize incoming bug reports.",
  "columns": [
    {"id": "col_new_001", "name": "New", "position": 0, "task_count": 0},
    {"id": "col_triaged_001", "name": "Triaged", "position": 1, "task_count": 0},
    {"id": "col_inprog_001", "name": "In Progress", "position": 2, "task_count": 0, "wip_limit": 5},
    {"id": "col_fixed_001", "name": "Fixed", "position": 3, "task_count": 0},
    {"id": "col_verified_001", "name": "Verified", "position": 4, "task_count": 0}
  ],
  "default_column_id": "col_new_001",
  "task_count": 0,
  "created_at": "2026-07-14T12:00:00Z",
  "updated_at": "2026-07-14T12:00:00Z"
}
```

## Retrieve a Board

Retrieve a board including its columns and the tasks in each column:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/boards/board_003?include_tasks=true&task_limit=10"
```

### Query Parameters for Board Detail

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `include_tasks` | boolean | false | Include task summaries nested within each column |
| `task_limit` | integer | 20 | Maximum tasks per column when `include_tasks` is true |

## Update a Board

```bash
curl -X PATCH https://api.taskmoor.com/v2/boards/board_003 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sprint Board - Q3",
    "columns": [
      {"id": "col_in_progress", "wip_limit": 8}
    ]
  }'
```

When updating columns, include the column `id` to modify existing columns. Columns not referenced in the update are unchanged.

## Delete a Board

```bash
curl -X DELETE https://api.taskmoor.com/v2/boards/board_003 \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content`. Deleting a board does not delete the tasks on it; tasks remain in the project and can be assigned to other boards.

## Error Handling

### BOARD_ERR_RENDER

If the Boards API encounters a rendering error when returning board data with nested tasks, it returns:

```json
{
  "error": {
    "code": "BOARD_ERR_RENDER",
    "message": "Board failed to load. Retry the request or contact support.",
    "request_id": "req_01XYZ789"
  }
}
```

This is a transient server-side error. Retry the request after a short delay. If the error persists, contact Taskmoor support with the `request_id`.

## Moving Tasks Between Columns

To move a task to a different column, update the task's `column_id`:

```bash
curl -X PATCH https://api.taskmoor.com/v2/tasks/task_042 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "column_id": "col_review"
  }'
```

If the target column has a WIP limit and is at capacity, the API returns `422 Unprocessable Entity` with a message indicating the column is full.
