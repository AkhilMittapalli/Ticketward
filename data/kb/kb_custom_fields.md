---
doc_key: kb_custom_fields
doc_type: help_article
title: "Creating and Using Custom Fields"
product_areas:
  - projects_tasks
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

Custom fields allow you to add structured data to tasks beyond the built-in fields (title, status, priority, assignee, due date, labels). You can create fields for tracking estimates, sprint numbers, customer names, cost values, or any other data specific to your workflow. Custom fields are available on Starter, Business, and Enterprise plans.

## Custom Field Types

Taskmoor supports the following custom field types:

| Field Type | Description | Example |
|---|---|---|
| **Text** | Single-line text input | Customer name, reference ID |
| **Number** | Numeric value (integer or decimal) | Story points, cost, hours |
| **Date** | Date picker | Target release date, review date |
| **Dropdown** | Single-select from predefined options | Sprint, department, severity |
| **Multi-select** | Multiple selections from predefined options | Affected platforms, required skills |
| **Checkbox** | True/false toggle | Approved, requires review |
| **URL** | Clickable hyperlink | Design spec link, PR URL |
| **Email** | Email address | Customer contact |
| **Currency** | Numeric value with currency symbol | Budget, actual cost |

## Creating a Custom Field

### Project-Level Custom Fields

1. Navigate to **Project Settings > Custom Fields**.
2. Click **+ New Field**.
3. Enter the field name (e.g., "Story Points").
4. Select the field type.
5. Configure type-specific options:
   - For **Dropdown** and **Multi-select**: Add the list of options.
   - For **Number** and **Currency**: Optionally set min/max values.
   - For **Currency**: Select the currency symbol (USD, EUR, GBP, etc.).
6. Set the field as **Required** or **Optional**. Required fields must be filled when creating or editing a task.
7. Click **Save**.

The custom field immediately appears on all tasks in the project.

### Workspace-Level Custom Fields (Business+)

On Business and Enterprise plans, workspace admins can create custom fields that span all projects:

1. Go to **Workspace Settings > Custom Fields**.
2. Follow the same steps as project-level creation.
3. Workspace-level fields appear on tasks in every project and maintain consistent options across the workspace.

## Setting Custom Field Values on Tasks

1. Open a task.
2. In the task detail panel, scroll to the **Custom Fields** section.
3. Click on a custom field to set or edit its value.
4. The value is saved automatically.

### Bulk Editing Custom Fields

To update a custom field on multiple tasks at once:

1. In the project List View, select multiple tasks using the checkboxes.
2. Click **Bulk Edit** in the toolbar.
3. Select the custom field and set the new value.
4. Click **Apply**.

All selected tasks are updated.

## Filtering and Sorting by Custom Fields

Custom fields can be used in filters and sort orders throughout Taskmoor:

- **List View**: Click **Filter** and select a custom field. Choose an operator (equals, does not equal, is empty, is not empty, greater than, less than) and a value.
- **Board View**: Custom fields are available as filter criteria but do not affect card grouping.
- **Timeline View**: Filter tasks by custom field values.
- **Reports/Dashboards**: Use custom field aggregation widgets (sum, average, count) on dashboards (Starter+).

To sort by a custom field in List View, click the column header for the custom field.

## Custom Fields in Automations

Automation rules (Starter+) can use custom fields as both triggers and action targets:

- **Trigger**: "When custom field 'Sprint' changes to 'Sprint 5', then..."
- **Condition**: "If custom field 'Story Points' is greater than 8, then..."
- **Action**: "Set custom field 'Reviewed' to true"

## Custom Fields in Imports

When importing tasks via CSV or Excel, prefix custom field column headers with `custom_` followed by the field name. For example, a field named "Sprint" should use the column header `custom_Sprint`. Values must match the field type (e.g., dropdown values must match one of the predefined options exactly).

## Limits

| Plan | Max Custom Fields per Project | Max Custom Fields per Workspace |
|---|---|---|
| Starter | 20 | N/A (project-level only) |
| Business | 50 | 100 |
| Enterprise | Unlimited | Unlimited |

## Troubleshooting

### Custom Field Not Appearing on Tasks

- Verify the field was created in the correct project (or at the workspace level for Business+ plans).
- If the field was created after an import, it will not retroactively populate existing tasks. Set values manually or via bulk edit.

### Dropdown Options Not Matching on Import

Imported values must match dropdown options exactly (case-insensitive). If the dropdown has "High Priority" but the CSV contains "high priority", the match succeeds. If the CSV contains "HP", the value is not recognized and the field is left empty with a warning in the import summary.

## Related Articles

- Importing Data via CSV
- Importing Data via Excel
- Creating Automation Rules
