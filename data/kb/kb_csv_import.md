---
doc_key: kb_csv_import
doc_type: help_article
title: "Importing Data via CSV"
product_areas:
  - data_import_export
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

Taskmoor supports importing tasks, projects, and other data from CSV files on all plans. CSV import is useful for migrating data from other tools, bulk-creating tasks, or loading data from spreadsheets.

## Supported Import Types

- **Tasks** -- Import tasks with titles, descriptions, statuses, priorities, assignees, due dates, labels, and custom fields (Starter+ for custom fields).
- **Members** -- Import a list of members to invite to the workspace (email addresses and roles).

## Preparing Your CSV File

### Required Format

- The file must be a valid CSV with UTF-8 encoding.
- The first row must be a header row with column names.
- Each subsequent row represents one record (e.g., one task).
- Use commas as delimiters. If your data contains commas, enclose the field in double quotes.

### Column Mapping for Task Import

Taskmoor recognizes the following column headers. Column names are case-insensitive:

| Column Name | Required | Description |
|---|---|---|
| `title` | Yes | The task title (max 500 characters) |
| `description` | No | Task description (plain text, max 10,000 characters) |
| `status` | No | Must match an existing status in the target project |
| `priority` | No | One of: low, medium, high, urgent |
| `assignee` | No | Email address of an existing workspace member |
| `due_date` | No | Date in ISO 8601 format (YYYY-MM-DD) |
| `labels` | No | Semicolon-separated list of labels (e.g., "bug;frontend") |
| `parent_task` | No | Title of an existing task to create this as a subtask of |
| `custom_*` | No | Custom field values, prefixed with `custom_` (Starter+ plans) |

### Example CSV

```
title,status,priority,assignee,due_date,labels
"Fix login page timeout",To Do,high,alice@company.com,2026-09-15,bug;frontend
"Update API documentation",In Progress,medium,bob@company.com,2026-09-20,docs
"Design new dashboard",To Do,low,,2026-10-01,design;ux
```

## Importing a CSV File

1. Navigate to the project where you want to import tasks.
2. Click the **gear icon** to open **Project Settings**.
3. Select **Import > CSV Import**.
4. Click **Choose File** and select your CSV file.
5. Taskmoor displays a **Column Mapping** preview:
   - Each column from your CSV is shown with a dropdown to map it to a Taskmoor field.
   - Taskmoor auto-maps columns based on header names. Verify and adjust if needed.
   - Any unmapped columns are ignored.
6. Review the **Import Preview** showing the first 5 rows as they will appear in Taskmoor.
7. Click **Start Import**.

## Import Limits

| Plan | Max Rows per Import | Max File Size |
|---|---|---|
| Free | 500 | 10 MB |
| Starter | 5,000 | 100 MB |
| Business | 25,000 | 250 MB |
| Enterprise | 100,000 | 1 GB |

## Import Behavior

- **Duplicate detection**: Taskmoor does not automatically deduplicate. If you import the same CSV twice, duplicate tasks are created. Use the import preview to verify before proceeding.
- **Status matching**: If a status value in the CSV does not match any existing status in the project, the task is created with the project's default status. A warning is shown in the import summary.
- **Assignee matching**: Assignees are matched by email address. If the email does not correspond to a workspace member, the task is created without an assignee and a warning is logged.
- **Custom fields**: Custom field columns (prefixed with `custom_`) are matched by field name. If the field does not exist in the project, the column is ignored.

## Reviewing Import Results

After the import completes, Taskmoor displays a summary:

- **Tasks created**: Number of tasks successfully imported.
- **Warnings**: Issues such as unmatched statuses, unknown assignees, or skipped custom fields.
- **Errors**: Rows that failed to import entirely (e.g., missing required `title` column).

You can download the import summary as a CSV file for reference.

## Troubleshooting

### IMP_ERR_ENCODING

This error indicates the CSV file is not in UTF-8 encoding. To fix this:

- Open the file in a text editor that supports encoding conversion (e.g., Notepad++ or VS Code).
- Save the file as **UTF-8 (without BOM)**.
- Re-upload the file.

### IMP_ERR_ROWS

This error appears when the CSV exceeds the maximum row limit for your plan. Split the file into smaller batches and import each one separately.

### Malformed CSV

If Taskmoor cannot parse your CSV, check for:

- Missing closing quotes on fields that contain commas or newlines.
- Inconsistent number of columns across rows.
- Non-standard line endings (use LF or CRLF consistently).

## Related Articles

- Importing Data via Excel
- Exporting to PDF
- Workspace Export
