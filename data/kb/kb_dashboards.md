---
doc_key: kb_dashboards
doc_type: help_article
title: "Creating and Managing Dashboards"
product_areas:
  - reporting_analytics
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

Dashboards in Taskmoor provide a visual summary of project and workspace activity through configurable widgets. You can build custom dashboards to track task progress, team performance, upcoming deadlines, and more. Dashboards are available on Starter, Business, and Enterprise plans.

## Prerequisites

- Your workspace must be on a **Starter**, **Business**, or **Enterprise** plan.
- You must have at least **Member** role to create personal dashboards.
- To create shared dashboards visible to the entire workspace, you need **Admin** role.

## Creating a Dashboard

1. In the Taskmoor sidebar, click **Dashboards**.
2. Click **+ New Dashboard**.
3. Enter a name for your dashboard (e.g., "Q3 Sprint Overview" or "Engineering Velocity").
4. Choose the visibility:
   - **Personal** -- Only you can see this dashboard.
   - **Shared** -- All workspace members can view it (Admin role required to create shared dashboards).
5. Click **Create**.

## Adding Widgets

After creating a dashboard, add widgets to populate it with data:

1. Click **+ Add Widget** in the dashboard toolbar.
2. Select a widget type:

| Widget Type | Description | Plan Required |
|---|---|---|
| Task Status Breakdown | Pie or bar chart of task statuses across selected projects | Starter+ |
| Tasks by Assignee | Bar chart showing task counts per team member | Starter+ |
| Due Date Timeline | Calendar heatmap of upcoming due dates | Starter+ |
| Overdue Tasks List | Table listing all overdue tasks with assignees and due dates | Starter+ |
| Recently Completed | Feed of tasks completed in the last 7/14/30 days | Starter+ |
| Workload Summary | Heatmap of assigned task hours per team member | Business+ |
| Time Tracking Summary | Total tracked time by project or member | Business+ |
| Automation Run Stats | Chart of automation rule executions over time | Business+ |
| Custom Field Aggregation | Aggregate numeric custom fields (sum, average, count) | Starter+ |

3. Configure the widget:
   - **Data Source**: Select one or more projects or the entire workspace.
   - **Filters**: Narrow data by status, assignee, label, priority, or date range.
   - **Chart Type**: Choose from pie, bar, line, or table (where applicable).
   - **Time Range**: Set to last 7 days, 30 days, 90 days, or custom.
4. Click **Add to Dashboard**.

## Arranging and Resizing Widgets

Widgets can be dragged and dropped to reorder them on the dashboard. To resize a widget, hover over its bottom-right corner and drag to the desired size. Dashboards support a flexible grid layout with widgets snapping to alignment.

## Editing and Removing Widgets

- To edit a widget, click the **three-dot menu** on the widget header and select **Edit**. Modify the configuration and click **Save**.
- To remove a widget, click the three-dot menu and select **Remove**. This does not delete any underlying data.

## Filtering the Entire Dashboard

Use the dashboard-level filter bar to apply a global filter across all widgets simultaneously. For example, filter the entire dashboard to show data for a single project or a specific date range. Widget-level filters are applied in addition to dashboard-level filters.

## Sharing and Permissions

- **Shared dashboards** are read-only for non-admin members. Admins can edit shared dashboards.
- To share a personal dashboard, click the **Share** button in the dashboard toolbar, change visibility to **Shared**, and save.
- Enterprise plans support fine-grained dashboard permissions, allowing you to share dashboards with specific teams or roles.

## Scheduled Dashboard Snapshots (Enterprise)

On Enterprise plans, you can schedule automatic snapshots of a dashboard to be emailed as a PDF:

1. Open the dashboard and click **Schedule Export**.
2. Set the frequency (daily, weekly, or monthly) and recipients.
3. Click **Save Schedule**.

For more details, see the Scheduled Report Exports article.

## Troubleshooting

### RPT_ERR_TIMEOUT

This error occurs when a dashboard widget query exceeds the 30-second timeout. Common causes include widgets configured to aggregate data across too many projects or very large date ranges. To resolve this, narrow the data source to fewer projects or reduce the time range.

### Widget Showing No Data

- Verify that the selected projects contain tasks matching the widget filters.
- Ensure you have access to the projects selected in the widget data source. If you lack access, the widget displays no data rather than an error.
- Check that the time range includes relevant activity.

## Related Articles

- Workload Reporting
- Time Tracking Reports
- Scheduled Report Exports
