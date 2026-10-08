---
doc_key: kb_workspace_export
doc_type: help_article
title: "Exporting Your Workspace Data"
product_areas:
  - data_import_export
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Workspace export allows you to download a complete archive of your Taskmoor workspace data, including all projects, tasks, comments, attachments, custom fields, and member information. This feature is available on Business and Enterprise plans and is useful for data backups, compliance audits, migrations to other platforms, or archival purposes.

## Prerequisites

- Your workspace must be on a **Business** or **Enterprise** plan.
- You must have **Workspace Admin** role to initiate a workspace export.
- Workspace exports can be large. Ensure you have sufficient storage to download the archive.

## Initiating a Workspace Export

1. Go to **Workspace Settings > Data Management**.
2. Click **Export Workspace**.
3. Choose the export scope:
   - **Full export** -- All projects, tasks, comments, attachments, members, and settings.
   - **Projects only** -- Select specific projects to include in the export.
   - **Exclude attachments** -- Export all metadata but skip file attachments to reduce archive size.
4. Choose the export format:
   - **JSON** -- Machine-readable format, suitable for programmatic processing or migration scripts.
   - **CSV bundle** -- A ZIP file containing separate CSV files for tasks, comments, members, and custom fields.
5. Click **Start Export**.

Taskmoor generates the export in the background. You receive an email notification when the export is ready to download.

## Export Contents

### JSON Export Structure

The JSON export produces a single ZIP archive containing:

```
workspace_export/
  workspace.json        -- Workspace settings, plan info, regions
  members.json          -- All members with roles and emails
  projects/
    project_<id>.json   -- Project settings, statuses, labels
    tasks_<id>.json     -- All tasks with subtasks, comments, history
    custom_fields_<id>.json -- Custom field definitions and values
  attachments/          -- File attachments (unless excluded)
    <file_id>_<filename>
```

### CSV Bundle Structure

The CSV bundle contains:

- `tasks.csv` -- All tasks across selected projects.
- `comments.csv` -- All comments linked to task IDs.
- `members.csv` -- Workspace members and their roles.
- `custom_fields.csv` -- Custom field definitions.
- `custom_field_values.csv` -- Custom field values per task.
- `attachments_index.csv` -- Metadata about attachments (filename, size, task ID).

Attachments are included as separate files in the ZIP archive.

## Export Processing Time

Export time depends on workspace size:

| Workspace Size | Estimated Time |
|---|---|
| < 1,000 tasks | Under 5 minutes |
| 1,000 - 10,000 tasks | 5 - 30 minutes |
| 10,000 - 100,000 tasks | 30 minutes to 2 hours |
| > 100,000 tasks | 2 - 8 hours |

Taskmoor processes exports in a background queue. You can continue using Taskmoor while the export runs.

## Download and Retention

- Once the export is ready, download it from **Workspace Settings > Data Management > Export History**.
- Export archives are retained for **7 days** after generation. After that, they are automatically deleted. If you need the export again, you must initiate a new one.
- The download link is unique and accessible only to workspace admins.

## Security and Compliance

- Workspace exports contain sensitive data including member email addresses, task contents, and attachments. Handle the exported archive according to your organization's data security policies.
- On Enterprise plans with audit logging enabled, workspace export events are recorded in the audit log with the initiating admin's identity and timestamp.
- The export does not include user passwords, API tokens, or SSO configuration secrets.

## Troubleshooting

### EXP_ERR_SIZE

This error occurs when the total export size exceeds the maximum allowed:

- **Business**: 50 GB maximum export size.
- **Enterprise**: 200 GB maximum export size.

To resolve, try exporting specific projects instead of the full workspace, or exclude attachments to reduce the file size.

### Export Stuck in "Processing"

If an export shows "Processing" status for more than 8 hours:

1. Check the **Export History** for any error messages.
2. Cancel the export by clicking **Cancel** next to the processing entry.
3. Retry the export. If the issue persists, try exporting smaller batches of projects.
4. Contact Taskmoor support if repeated exports fail.

### Missing Data in Export

- Archived projects are not included in workspace exports by default. To include archived projects, select the **Include Archived Projects** checkbox when configuring the export.
- Tasks deleted before the export was initiated are not included. Only tasks present at the time the export job begins are captured.

## Related Articles

- Exporting to PDF
- Importing Data via CSV
- Importing Data via Excel
