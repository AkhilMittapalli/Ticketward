---
doc_key: pd_export_api
doc_type: product_doc
title: "Export API: Workspace and Report Exports"
product_areas:
  - data_import_export
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-05"
effective_from: "2026-07-09"
effective_to: null
---

## Overview

The Taskmoor Export API enables programmatic export of workspace data including tasks, projects, time entries, and analytics reports. Workspace exports are available on Business and Enterprise plans. Enterprise customers can additionally schedule recurring report exports via the API.

## Triggering an Export

Create an export job by sending a POST request to `/v2/exports`:

```bash
curl -X POST https://api.taskmoor.com/v2/exports \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "workspace",
    "format": "json",
    "scope": {
      "projects": ["proj_001", "proj_002"],
      "date_range": {
        "from": "2026-01-01",
        "to": "2026-06-30"
      }
    },
    "include": ["tasks", "comments", "time_entries", "attachments_metadata"]
  }'
```

Response:

```json
{
  "id": "exp_01ABC",
  "type": "workspace",
  "format": "json",
  "status": "processing",
  "created_at": "2026-07-09T11:00:00Z",
  "estimated_completion": "2026-07-09T11:05:00Z"
}
```

### Export Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `type` | string | Yes | Export type: `workspace`, `report`, or `audit_log` |
| `format` | string | Yes | Output format: `json`, `csv`, or `pdf` |
| `scope.projects` | array | No | Project IDs to include (default: all projects) |
| `scope.date_range.from` | string | No | Start date filter (ISO 8601 date) |
| `scope.date_range.to` | string | No | End date filter (ISO 8601 date) |
| `include` | array | No | Data types to include in the export |

### Exportable Data Types

| Data Type | Description | Plan |
|-----------|-------------|------|
| `tasks` | All task records with metadata | Business+ |
| `comments` | Task comments and replies | Business+ |
| `time_entries` | Time tracking records | Business+ |
| `attachments_metadata` | File attachment metadata (not file contents) | Business+ |
| `projects` | Project configuration and metadata | Business+ |
| `boards` | Board layouts and column definitions | Business+ |
| `audit_log` | Workspace audit trail events | Enterprise |

### Export Formats

| Format | Description | Max Size |
|--------|-------------|:--------:|
| `json` | Structured JSON with nested relationships | 2 GB |
| `csv` | Flat CSV with one file per data type (delivered as ZIP) | 2 GB |
| `pdf` | Formatted report (report exports only) | 100 MB |

## Checking Export Status

Poll the export status until it completes:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/exports/exp_01ABC"
```

Response when complete:

```json
{
  "id": "exp_01ABC",
  "type": "workspace",
  "format": "json",
  "status": "completed",
  "download_url": "https://exports.taskmoor.com/exp_01ABC/download?token=dl_temp_xyz",
  "file_size_bytes": 15728640,
  "expires_at": "2026-07-16T11:00:00Z",
  "created_at": "2026-07-09T11:00:00Z",
  "completed_at": "2026-07-09T11:03:22Z"
}
```

### Export Statuses

| Status | Description |
|--------|-------------|
| `processing` | Export is being generated |
| `completed` | Export is ready for download |
| `failed` | Export generation failed |
| `expired` | Download link has expired |

## Downloading the Export

The `download_url` is a pre-signed URL valid for 7 days:

```bash
curl -o workspace_export.json \
  "https://exports.taskmoor.com/exp_01ABC/download?token=dl_temp_xyz"
```

## Listing Past Exports

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/exports?limit=10"
```

## Scheduled Report Exports (Enterprise)

Enterprise customers can create recurring export schedules:

```bash
curl -X POST https://api.taskmoor.com/v2/exports/schedules \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Weekly project status",
    "type": "report",
    "format": "pdf",
    "schedule": "weekly",
    "day_of_week": "monday",
    "time": "08:00",
    "timezone": "America/New_York",
    "scope": {
      "projects": ["proj_001"]
    },
    "delivery": {
      "method": "email",
      "recipients": ["pm@example.com", "lead@example.com"]
    }
  }'
```

### Schedule Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `schedule` | string | Frequency: `daily`, `weekly`, `monthly` |
| `day_of_week` | string | Day for weekly schedules (e.g., `monday`) |
| `day_of_month` | integer | Day for monthly schedules (1-28) |
| `time` | string | Time in HH:MM format |
| `timezone` | string | IANA timezone for scheduling |
| `delivery.method` | string | `email` or `webhook` |
| `delivery.recipients` | array | Email addresses for email delivery |
| `delivery.webhook_url` | string | URL for webhook delivery (receives download link) |

## Error Handling

### EXP_ERR_SIZE: Export Too Large

When the requested export exceeds the maximum file size:

```json
{
  "error": {
    "code": "EXP_ERR_SIZE",
    "message": "Export exceeds the maximum size of 2GB. Apply date range filters or reduce the scope.",
    "details": {
      "estimated_size_bytes": 3221225472,
      "max_size_bytes": 2147483648
    }
  }
}
```

**Resolution**: Narrow the export scope by adding project filters or restricting the date range. For very large workspaces, export in incremental date-range batches.

## Export Data Retention

Completed exports are available for download for 7 days. After expiration, the export file is permanently deleted. The export metadata (status, parameters) is retained for 90 days in the export history.
