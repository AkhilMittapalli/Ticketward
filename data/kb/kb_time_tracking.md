---
doc_key: kb_time_tracking
doc_type: help_article
title: "Time Tracking and Reports"
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

Taskmoor's time tracking feature lets team members log time spent on tasks and generates reports to help managers understand where effort is being invested. Time tracking is available on Business and Enterprise plans.

## Enabling Time Tracking

Time tracking must be enabled at the workspace level by an administrator:

1. Go to **Workspace Settings > Features**.
2. Toggle **Time Tracking** to on.
3. Click **Save**.

Once enabled, a time tracking control appears on every task detail view across all projects in the workspace.

## Logging Time on a Task

### Using the Timer

1. Open a task and locate the **Time Tracking** section in the task detail panel.
2. Click **Start Timer** to begin tracking.
3. Work on the task. The timer runs even if you navigate away or close the tab (it is server-side).
4. Return to the task and click **Stop Timer** to record the elapsed time.
5. Optionally, add a description for the time entry (e.g., "Code review and feedback").

### Manual Time Entry

1. Open a task and go to the **Time Tracking** section.
2. Click **Log Time**.
3. Enter the date, duration (hours and minutes), and an optional description.
4. Click **Save**.

You can log time in increments as small as 1 minute.

### Mobile Time Tracking

Time tracking is fully supported in the Taskmoor mobile apps (iOS 5.8.2+ and Android 5.8.1+). The timer widget is accessible from the task detail screen. Running timers sync across devices, so you can start a timer on mobile and stop it on the web or desktop app.

## Viewing Time Tracking Reports

### Task-Level Summary

Each task displays a total tracked time summary showing all entries by all contributors. Click **View Details** to see individual time entries with timestamps, durations, and descriptions.

### Project-Level Report

1. Navigate to **Reports > Time Tracking**.
2. Select a project.
3. Choose a date range.
4. The report shows:
   - **Total hours tracked** across the project.
   - **Hours by member**: A bar chart showing who logged the most time.
   - **Hours by task**: Ranked list of tasks by total logged time.
   - **Hours by day/week**: Trend line showing time tracked over the selected period.

### Workspace-Level Report

Select **All Projects** in the project filter to generate a workspace-wide time tracking report. This is useful for billing reviews, capacity planning, or timesheet verification.

## Editing and Deleting Time Entries

- **Editing**: Click on any time entry in the task detail view or report drill-down and modify the date, duration, or description. Only the person who logged the entry or a workspace admin can edit it.
- **Deleting**: Click the three-dot menu on a time entry and select **Delete**. Deleted entries are removed from all reports. This action cannot be undone.

## Exporting Time Data

1. In the **Time Tracking** report, click **Export**.
2. Choose **CSV** or **PDF**.
3. The CSV export includes columns for task ID, task title, project, member, date, duration, and description, making it suitable for import into external billing or payroll systems.

Enterprise plans can schedule recurring time tracking report exports. See the Scheduled Report Exports article.

## Rounding and Billing Rules

Taskmoor records time to the exact minute. If your organization uses billing increments (e.g., 15-minute blocks), apply rounding after export in your billing tool. Taskmoor does not automatically round time entries.

## Troubleshooting

### Timer Not Syncing Across Devices

Ensure you are signed in to the same Taskmoor account on all devices. If the timer shows a different state on different devices, force-close and reopen the app to refresh the session. If MOB_ERR_SESSION appears, sign out and back in to reset the session.

### RPT_ERR_TIMEOUT on Time Reports

Time tracking reports for large workspaces with thousands of entries may time out (RPT_ERR_TIMEOUT). Narrow the date range or filter to specific projects to reduce the data set.

## Related Articles

- Workload Reporting
- Creating Dashboards
- Scheduled Report Exports
