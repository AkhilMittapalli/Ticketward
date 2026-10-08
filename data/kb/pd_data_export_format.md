---
doc_key: pd_data_export_format
doc_type: product_doc
title: "Data Export Format Specification: CSV, JSON, PDF"
product_areas:
  - data_import_export
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-26"
effective_from: "2026-07-30"
effective_to: null
---

## Overview

Taskmoor supports three export formats for workspace data: JSON, CSV, and PDF. Each format serves different use cases, from programmatic data processing to human-readable reports. Data export is available on Business and Enterprise plans through the `/v2/exports` endpoint.

## JSON Export Format

JSON exports provide the richest data representation, preserving nested relationships and all metadata fields. JSON is recommended for programmatic consumption, data migration, and backup.

### File Structure

JSON exports are delivered as a single file containing an array of resources grouped by type:

```json
{
  "export_id": "exp_01ABC",
  "workspace_id": "ws_001",
  "exported_at": "2026-07-30T12:00:00Z",
  "format_version": "2.0",
  "data": {
    "projects": [
      {
        "id": "proj_001",
        "name": "Platform Redesign",
        "status": "active",
        "owner_id": "usr_001",
        "start_date": "2026-06-01",
        "target_date": "2026-09-30",
        "created_at": "2026-06-01T08:00:00Z",
        "updated_at": "2026-07-30T11:00:00Z"
      }
    ],
    "tasks": [
      {
        "id": "task_042",
        "title": "Implement OAuth flow",
        "description": "Add OAuth 2.0 authorization code flow.",
        "status": "in_progress",
        "priority": "high",
        "project_id": "proj_001",
        "assignee_id": "usr_007",
        "labels": ["backend", "security"],
        "due_date": "2026-07-25",
        "dependencies": ["task_040"],
        "created_at": "2026-07-10T09:00:00Z",
        "updated_at": "2026-07-30T10:30:00Z"
      }
    ],
    "comments": [
      {
        "id": "cmt_001",
        "task_id": "task_042",
        "author_id": "usr_007",
        "body": "Initial implementation is complete.",
        "created_at": "2026-07-16T10:30:00Z"
      }
    ],
    "time_entries": [
      {
        "id": "te_001",
        "task_id": "task_042",
        "user_id": "usr_007",
        "description": "OAuth token refresh logic",
        "started_at": "2026-07-20T09:00:00Z",
        "ended_at": "2026-07-20T11:30:00Z",
        "duration_seconds": 9000,
        "billable": true
      }
    ]
  }
}
```

### JSON Schema Details

| Field | Type | Description |
|-------|------|-------------|
| `export_id` | string | Unique export identifier |
| `workspace_id` | string | Source workspace |
| `exported_at` | string | ISO 8601 timestamp of export generation |
| `format_version` | string | Export schema version (currently `"2.0"`) |
| `data` | object | Resource collections keyed by type |

### Encoding

JSON exports use UTF-8 encoding. All string values are properly escaped per RFC 8259. Timestamps are ISO 8601 with UTC timezone. Null values are represented as JSON `null`.

## CSV Export Format

CSV exports are suited for spreadsheet analysis and import into business intelligence tools. Because CSV is a flat format, nested relationships are denormalized.

### File Delivery

CSV exports are delivered as a ZIP archive containing one CSV file per resource type:

```
workspace_export_2026-07-30.zip
  ├── projects.csv
  ├── tasks.csv
  ├── comments.csv
  └── time_entries.csv
```

### tasks.csv Column Reference

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Task identifier |
| `title` | string | Task title |
| `description` | string | Task description (Markdown stripped to plain text) |
| `status` | string | Current status |
| `priority` | string | Priority level |
| `project_id` | string | Parent project identifier |
| `project_name` | string | Parent project name (denormalized) |
| `assignee_id` | string | Assigned user identifier |
| `assignee_name` | string | Assigned user name (denormalized) |
| `assignee_email` | string | Assigned user email (denormalized) |
| `labels` | string | Pipe-delimited labels (e.g., `backend|security`) |
| `due_date` | string | Due date (YYYY-MM-DD) |
| `estimated_hours` | number | Estimated effort |
| `dependency_ids` | string | Pipe-delimited dependency task IDs |
| `comment_count` | integer | Number of comments |
| `attachment_count` | integer | Number of attachments |
| `created_at` | string | ISO 8601 creation timestamp |
| `updated_at` | string | ISO 8601 last update timestamp |

### CSV Encoding

- Character encoding: UTF-8 with BOM (for Excel compatibility)
- Delimiter: comma (`,`)
- Quoting: fields containing commas, newlines, or double quotes are enclosed in double quotes
- Line endings: CRLF (`\r\n`)
- Header row: always present as the first row
- Multi-value fields: pipe-delimited (`|`)

## PDF Export Format

PDF exports generate formatted reports suitable for stakeholder presentations and documentation. PDF format is available only for report-type exports (not full workspace exports).

### Report Types

| Report | Description | Content |
|--------|-------------|---------|
| Project Summary | Overview of project status and metrics | Task breakdown by status, burndown chart, timeline |
| Team Workload | Time allocation across team members | Hours by user, project, billable/non-billable split |
| Sprint Report | Sprint performance and velocity | Completed vs. planned tasks, carryover items |

### Triggering a PDF Report Export

```bash
curl -X POST https://api.taskmoor.com/v2/exports \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "report",
    "format": "pdf",
    "report_type": "project_summary",
    "scope": {
      "projects": ["proj_001"],
      "date_range": {
        "from": "2026-07-01",
        "to": "2026-07-31"
      }
    }
  }'
```

### PDF Specifications

| Property | Value |
|----------|-------|
| Page size | Letter (8.5 x 11 inches) |
| Max pages | 200 |
| Max file size | 100 MB |
| Fonts | Embedded (no external dependencies) |
| Color mode | CMYK-safe colors |

## Data Import Compatibility

### Importing from CSV

Taskmoor can re-import CSV files generated by the export. The import endpoint validates:

- **Encoding**: Must be UTF-8. Files with other encodings return `IMP_ERR_ENCODING`.
- **Row limit**: Maximum 50,000 rows per file. Files exceeding this limit return `IMP_ERR_ROWS`.
- **Column mapping**: Column headers must match the export schema or be manually mapped during import.

### Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| `IMP_ERR_ENCODING` | File uses unsupported encoding | Re-save as UTF-8 |
| `IMP_ERR_ROWS` | File exceeds 50,000 row limit | Split into smaller files |
| `EXP_ERR_SIZE` | Export exceeds maximum file size | Narrow the scope with date range or project filters |

## Export Size Limits

| Format | Maximum Size |
|--------|:------------:|
| JSON | 2 GB |
| CSV (ZIP) | 2 GB |
| PDF | 100 MB |

If an export would exceed these limits, the API returns `EXP_ERR_SIZE` before processing begins, with the estimated size in the error details.
