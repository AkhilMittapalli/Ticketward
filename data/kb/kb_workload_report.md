---
doc_key: kb_workload_report
doc_type: help_article
title: "Using the Workload Report"
product_areas:
  - reporting_analytics
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

The workload report provides a visual overview of how tasks and effort are distributed across team members. It helps project managers identify overloaded or underutilized team members and rebalance work before deadlines are missed. The workload report is available on Business and Enterprise plans.

## Accessing the Workload Report

1. In the Taskmoor sidebar, navigate to **Reports**.
2. Click **Workload Report**.
3. Select the project(s) or the entire workspace you want to analyze.
4. Choose a date range for the report.

## Understanding the Workload View

The workload report displays a heatmap-style grid with team members along the vertical axis and time periods (days or weeks) along the horizontal axis. Each cell is color-coded to indicate the volume of assigned tasks or estimated effort:

- **Green**: Within capacity (task count or hours below the defined threshold).
- **Yellow**: Approaching capacity (75-100% of threshold).
- **Red**: Over capacity (exceeds threshold).
- **Gray**: No tasks assigned in that period.

### Capacity Thresholds

By default, Taskmoor uses a threshold of 8 tasks per day per member. You can customize this threshold:

1. In the workload report toolbar, click **Settings**.
2. Under **Capacity Mode**, choose:
   - **Task count** -- Capacity measured by number of assigned tasks.
   - **Estimated hours** -- Capacity measured by the sum of estimated hours in custom fields (requires a numeric custom field named "Estimate" or "Hours").
3. Set the daily or weekly threshold.
4. Click **Apply**.

## Filtering the Report

Use the filter bar above the report to narrow results:

- **Assignee**: Show specific team members only.
- **Project**: Limit to one or more projects.
- **Status**: Include only tasks in certain statuses (e.g., exclude completed tasks).
- **Priority**: Filter by priority level.
- **Label**: Filter by task labels.

Filters are applied in real time and the heatmap updates accordingly.

## Drill-Down

Click any cell in the heatmap to drill down into the specific tasks assigned to that team member for that time period. A panel opens on the right showing:

- Task titles with links to open each task
- Status, priority, and due date for each task
- Estimated effort (if using estimated hours mode)

From the drill-down panel, you can reassign tasks directly by clicking the assignee avatar and selecting a different team member.

## Exporting the Workload Report

To export the report:

1. Click **Export** in the report toolbar.
2. Choose the format:
   - **PDF** -- A snapshot of the current view, suitable for sharing in presentations.
   - **CSV** -- Raw data including member names, dates, task counts, and estimated hours.
3. Click **Download**.

Enterprise plans can schedule automatic exports. See the Scheduled Report Exports article for details.

## Troubleshooting

### RPT_ERR_TIMEOUT

The workload report may time out if you select too many projects or a very wide date range. To avoid RPT_ERR_TIMEOUT:

- Narrow the date range to 30 days or less.
- Select fewer projects (5 or fewer is recommended for large workspaces).
- Apply filters to reduce the data set.

### Capacity Colors Not Displaying Correctly

Ensure you have configured the capacity threshold under the report settings. If using estimated hours mode, verify that the relevant custom field exists and is populated on tasks. Tasks without an estimate value are treated as zero hours and do not contribute to capacity calculations.

### Members Missing from the Report

The workload report includes only members who have at least one task assigned in the selected projects and date range. If a team member does not appear, verify they have assigned tasks in the filtered scope. Guest users are included only if they have task assignments.

## Related Articles

- Creating Dashboards
- Time Tracking Reports
- Custom Fields
