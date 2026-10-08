---
doc_key: pd_time_entry_api
doc_type: product_doc
title: "Time Entries API Endpoint Reference"
product_areas:
  - integrations_api
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-16"
effective_from: "2026-07-20"
effective_to: null
---

## Overview

The Time Entries API enables tracking and querying time spent on tasks within Taskmoor workspaces. Time entries record the duration, user, task, and optional description for each work session. This endpoint is available on Business and Enterprise plans.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v2/time-entries` | List time entries with filters |
| `POST` | `/v2/time-entries` | Create a time entry |
| `GET` | `/v2/time-entries/{entry_id}` | Retrieve a single time entry |
| `PATCH` | `/v2/time-entries/{entry_id}` | Update a time entry |
| `DELETE` | `/v2/time-entries/{entry_id}` | Delete a time entry |

## List Time Entries

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/time-entries?task_id=task_042&limit=20"
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `task_id` | string | null | Filter by task |
| `project_id` | string | null | Filter by project |
| `user_id` | string | null | Filter by user |
| `started_after` | string | null | Entries started after this ISO 8601 timestamp |
| `started_before` | string | null | Entries started before this ISO 8601 timestamp |
| `billable` | boolean | null | Filter by billable status |
| `sort` | string | `started_at` | Sort field: `started_at`, `duration`, `created_at` |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `limit` | integer | 50 | Results per page (max: 100) |
| `cursor` | string | null | Pagination cursor |

### Response

```json
{
  "data": [
    {
      "id": "te_001",
      "task_id": "task_042",
      "project_id": "proj_001",
      "user_id": "usr_007",
      "user": {
        "id": "usr_007",
        "name": "Jordan Lee"
      },
      "description": "Implemented OAuth token refresh logic",
      "started_at": "2026-07-20T09:00:00Z",
      "ended_at": "2026-07-20T11:30:00Z",
      "duration_seconds": 9000,
      "billable": true,
      "created_at": "2026-07-20T11:30:00Z",
      "updated_at": "2026-07-20T11:30:00Z"
    },
    {
      "id": "te_002",
      "task_id": "task_042",
      "project_id": "proj_001",
      "user_id": "usr_007",
      "user": {
        "id": "usr_007",
        "name": "Jordan Lee"
      },
      "description": "Code review and testing",
      "started_at": "2026-07-20T13:00:00Z",
      "ended_at": "2026-07-20T14:45:00Z",
      "duration_seconds": 6300,
      "billable": true,
      "created_at": "2026-07-20T14:45:00Z",
      "updated_at": "2026-07-20T14:45:00Z"
    }
  ],
  "pagination": {
    "cursor": null,
    "has_more": false,
    "total_count": 2
  }
}
```

## Create a Time Entry

### Manual Entry (start and end times)

```bash
curl -X POST https://api.taskmoor.com/v2/time-entries \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_042",
    "started_at": "2026-07-20T15:00:00Z",
    "ended_at": "2026-07-20T16:30:00Z",
    "description": "Writing unit tests for auth module",
    "billable": true
  }'
```

### Duration-Based Entry

```bash
curl -X POST https://api.taskmoor.com/v2/time-entries \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_042",
    "started_at": "2026-07-20T15:00:00Z",
    "duration_seconds": 5400,
    "description": "Writing unit tests for auth module",
    "billable": true
  }'
```

### Running Timer

Start a timer without specifying an end time:

```bash
curl -X POST https://api.taskmoor.com/v2/time-entries \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_042",
    "started_at": "2026-07-20T15:00:00Z",
    "description": "Debugging integration test failures"
  }'
```

Response for a running timer includes `"ended_at": null` and `"running": true`.

### Create Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `task_id` | string | Yes | Task the time entry is logged against |
| `started_at` | string | Yes | Start time in ISO 8601 format |
| `ended_at` | string | No | End time; omit to start a running timer |
| `duration_seconds` | integer | No | Duration in seconds (alternative to `ended_at`) |
| `description` | string | No | Description of work performed (max 1,000 characters) |
| `billable` | boolean | No | Whether the entry is billable (default: workspace setting) |

If both `ended_at` and `duration_seconds` are provided, `ended_at` takes precedence.

## Stop a Running Timer

Stop a running timer by setting the `ended_at` field:

```bash
curl -X PATCH https://api.taskmoor.com/v2/time-entries/te_003 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "ended_at": "2026-07-20T17:15:00Z"
  }'
```

## Update a Time Entry

```bash
curl -X PATCH https://api.taskmoor.com/v2/time-entries/te_001 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Implemented OAuth token refresh and added retry logic",
    "billable": false
  }'
```

## Delete a Time Entry

```bash
curl -X DELETE https://api.taskmoor.com/v2/time-entries/te_001 \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content`. Users can delete their own time entries. Workspace administrators can delete any time entry.

## Aggregation Queries

Get total time tracked per project within a date range:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/time-entries/summary?project_id=proj_001&started_after=2026-07-01T00:00:00Z&started_before=2026-07-31T23:59:59Z&group_by=user"
```

Response:

```json
{
  "project_id": "proj_001",
  "period": {
    "from": "2026-07-01T00:00:00Z",
    "to": "2026-07-31T23:59:59Z"
  },
  "total_seconds": 432000,
  "total_billable_seconds": 345600,
  "groups": [
    {"user_id": "usr_007", "name": "Jordan Lee", "total_seconds": 216000, "billable_seconds": 194400},
    {"user_id": "usr_012", "name": "Sam Rivera", "total_seconds": 144000, "billable_seconds": 108000},
    {"user_id": "usr_003", "name": "Chris Park", "total_seconds": 72000, "billable_seconds": 43200}
  ]
}
```

### Summary Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string | Project to summarize |
| `started_after` | string | Period start (ISO 8601) |
| `started_before` | string | Period end (ISO 8601) |
| `group_by` | string | Grouping: `user`, `task`, `day`, `week` |

## Error Responses

| HTTP Status | Description |
|:-----------:|-------------|
| 401 | Invalid or revoked API token (`API_ERR_401`) |
| 403 | Token lacks `time_entries:read` or `time_entries:write` scope |
| 404 | Time entry or task not found |
| 422 | Validation error (e.g., `ended_at` before `started_at`, overlapping running timer) |
