---
doc_key: kb_excel_import
doc_type: help_article
title: "Importing Data via Excel"
product_areas:
  - data_import_export
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

## Overview

Taskmoor supports importing tasks and project data from Microsoft Excel files (.xlsx) on Starter, Business, and Enterprise plans. Excel import preserves formatting context and supports multiple sheets, making it ideal for teams migrating from spreadsheet-based project tracking.

## Prerequisites

- Your workspace must be on a **Starter**, **Business**, or **Enterprise** plan.
- The Excel file must be in `.xlsx` format (the modern XML-based format). Older `.xls` files are not supported.
- You must have **Project Admin** or **Workspace Admin** role to perform imports.

## Preparing Your Excel File

### Sheet Structure

Taskmoor imports data from the **first sheet** in the workbook by default. You can select a different sheet during the import process.

Each row in the sheet represents one task. The first row must be headers. Supported columns are the same as CSV import:

| Column Name | Required | Description |
|---|---|---|
| `title` | Yes | Task title (max 500 characters) |
| `description` | No | Task description (plain text) |
| `status` | No | Must match an existing project status |
| `priority` | No | One of: low, medium, high, urgent |
| `assignee` | No | Email address of an existing workspace member |
| `due_date` | No | Date value (Excel date format or ISO 8601) |
| `labels` | No | Semicolon-separated labels |
| `parent_task` | No | Title of a parent task for subtask creation |
| `custom_*` | No | Custom field values (matched by field name) |

### Date Handling

Taskmoor recognizes dates stored as Excel date values (formatted cells) and text dates in ISO 8601 format (YYYY-MM-DD). If dates are stored as plain text in other formats (e.g., "Sept 15, 2026" or "15/09/2026"), Taskmoor may misinterpret them. For best results, format date columns as Excel Date cells or use ISO 8601 strings.

### Data Validation

Before importing, review your spreadsheet for:

- **Merged cells**: Taskmoor cannot parse merged cells. Unmerge all cells before importing.
- **Formulas**: Taskmoor imports the computed value, not the formula itself. Verify that formula results display correctly.
- **Hidden rows or columns**: Hidden rows are imported. Hidden columns are imported. Remove any rows or columns you do not want imported.
- **Filters**: Active filters do not affect the import. All rows in the sheet are imported regardless of filter state.

## Performing the Import

1. Open the target project in Taskmoor.
2. Go to **Project Settings > Import > Excel Import**.
3. Click **Choose File** and select your `.xlsx` file.
4. If the workbook contains multiple sheets, select the sheet to import from the dropdown.
5. Taskmoor displays a **Column Mapping** screen:
   - Review auto-mapped columns and correct any mismatches.
   - Map any custom field columns to existing custom fields in the project.
   - Unmapped columns are ignored.
6. Preview the first 10 rows to verify data accuracy.
7. Click **Start Import**.

## Import Limits

Import limits match those of CSV import and are based on your plan:

| Plan | Max Rows per Import | Max File Size |
|---|---|---|
| Starter | 5,000 | 100 MB |
| Business | 25,000 | 250 MB |
| Enterprise | 100,000 | 1 GB |

## Multi-Sheet Import

Taskmoor imports one sheet at a time. If your workbook contains tasks across multiple sheets (e.g., one sheet per project), perform a separate import for each sheet into the corresponding project.

## Import Results

After the import completes, Taskmoor provides a summary showing:

- Number of tasks successfully created
- Warnings for unmatched statuses, assignees, or custom fields
- Errors for rows missing the required `title` value

Download the import report from the summary screen for your records.

## Troubleshooting

### IMP_ERR_ENCODING

This error sometimes appears with Excel files that contain special characters in a non-standard code page. Ensure your Excel file is saved as a standard `.xlsx` file (not `.xls` or `.xlsm`). Re-save the file in Excel using **File > Save As > Excel Workbook (.xlsx)**.

### IMP_ERR_ROWS

The file contains more rows than your plan allows. Split the data across multiple files or upgrade to a higher plan.

### Dates Imported Incorrectly

If dates appear as serial numbers (e.g., 46347 instead of 2026-09-15), the date column was not formatted as a date type in Excel. Reformat the column as a Date in Excel, save, and re-import.

### Custom Fields Not Populating

Ensure the Excel column header matches the custom field name exactly (case-insensitive) and is prefixed with `custom_`. For example, a custom field named "Sprint" should have the column header `custom_Sprint` or `custom_sprint`.

## Related Articles

- Importing Data via CSV
- Custom Fields
- Workspace Export
