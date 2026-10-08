---
doc_key: kb_pdf_export
doc_type: help_article
title: "Exporting Tasks and Reports to PDF"
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

Taskmoor allows you to export individual tasks, task lists, board views, and reports as PDF files. PDF export is available on all plans and is useful for creating offline records, sharing project status with stakeholders who do not have Taskmoor accounts, or generating printable documentation.

## What You Can Export to PDF

### Individual Tasks

Export a single task with its full details:

1. Open the task you want to export.
2. Click the **three-dot menu** in the task header.
3. Select **Export to PDF**.
4. The PDF includes: task title, description, status, priority, assignee, due date, labels, subtasks, comments (most recent 50), custom field values (Starter+), and activity history.

### Task Lists

Export a filtered list of tasks from a project:

1. Navigate to the project's **List View**.
2. Apply any filters (status, assignee, priority, label, date range).
3. Click the **Export** button in the toolbar.
4. Select **PDF**.
5. The PDF contains a table of all visible tasks with columns for title, status, priority, assignee, and due date.

### Board Views

Export a snapshot of a Kanban board:

1. Open the project's **Board View**.
2. Click the **Export** button.
3. Select **PDF**.
4. The PDF renders the board layout with columns and cards, similar to what appears on screen.

### Reports (Starter+ Plans)

Export dashboards, workload reports, and time tracking reports:

1. Open the report or dashboard.
2. Click **Export** in the toolbar.
3. Select **PDF**.
4. Charts and tables are rendered as static images in the PDF.

## PDF Export Options

When exporting, you can configure the following options:

- **Page size**: Letter (8.5 x 11 in) or A4 (210 x 297 mm).
- **Orientation**: Portrait or Landscape.
- **Include comments**: Toggle whether task comments are included (for individual task exports).
- **Include activity history**: Toggle whether the task change log is included.
- **Header/Footer**: Optionally include the workspace name, project name, export date, and page numbers.

## PDF Generation

After clicking **Export**, Taskmoor generates the PDF in the background. For small exports (single tasks or short lists), the download starts immediately. For larger exports (full board views, long task lists, or reports with complex charts), generation may take up to 30 seconds. A progress indicator appears in the toolbar.

## Quality and Formatting

- Text in PDFs is searchable and selectable.
- Charts and board views are rendered as high-resolution images (300 DPI).
- Attachments are not included in PDF exports. Only attachment names and file sizes are listed.
- Hyperlinks within task descriptions are preserved as clickable links in the PDF.
- Custom field values appear in a dedicated section on individual task PDFs.

## Troubleshooting

### EXP_ERR_SIZE

This error appears when the generated PDF exceeds 100 MB (the maximum size for a single PDF export). This typically happens with very large task lists (over 10,000 tasks). To resolve:

- Apply filters to reduce the number of tasks in the export.
- Export in multiple batches (e.g., by status or date range).
- For large data exports, consider using CSV export or workspace export instead.

### Board View PDF Looks Truncated

If the Kanban board has many columns or cards, the PDF may truncate content to fit the page. Try switching to **Landscape** orientation or reducing the number of visible columns by filtering before export. On wide boards with more than 8 columns, consider exporting the List View instead.

### Charts Not Rendering in Report PDFs

If charts appear blank in a report PDF, ensure your browser allows Taskmoor to run JavaScript for PDF generation. Disable any browser extensions that block script execution on the Taskmoor domain. Alternatively, try exporting from a different browser or the Taskmoor desktop app.

### RPT_ERR_TIMEOUT

Report PDF exports that include complex dashboard widgets may time out. Simplify the dashboard by removing high-data-volume widgets or narrowing filters before exporting.

## Related Articles

- Importing Data via CSV
- Workspace Export
- Creating Dashboards
