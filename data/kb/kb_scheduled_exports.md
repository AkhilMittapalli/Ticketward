---
doc_key: kb_scheduled_exports
doc_type: help_article
title: "Scheduling Automatic Report Exports"
product_areas:
  - reporting_analytics
plans_applicable:
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Scheduled report exports allow Enterprise plan administrators to automatically generate and deliver reports on a recurring basis. Reports are exported as PDF or CSV files and delivered via email to specified recipients. This feature eliminates the need to manually run and distribute reports, ensuring stakeholders always have up-to-date data.

## Prerequisites

- Your workspace must be on an **Enterprise** plan.
- You must have **Workspace Admin** role to create or manage scheduled exports.
- Recipients must have a valid email address but do not need to be Taskmoor workspace members.

## Creating a Scheduled Export

1. Navigate to **Reports** in the Taskmoor sidebar.
2. Open the report you want to schedule (e.g., Workload Report, Time Tracking, or a Dashboard).
3. Configure the report with the desired filters, date range, and grouping options.
4. Click **Schedule Export** in the report toolbar.
5. Configure the schedule:

| Setting | Options |
|---|---|
| **Frequency** | Daily, Weekly, Monthly |
| **Day of Week** (weekly) | Monday through Sunday |
| **Day of Month** (monthly) | 1st through 28th, or Last Day |
| **Time** | Hour in your workspace timezone |
| **Format** | PDF, CSV, or Both |
| **Recipients** | Email addresses (comma-separated, up to 25) |
| **Subject Line** | Customizable; supports variables: `{report_name}`, `{date}`, `{workspace}` |

6. Click **Save Schedule**.

The first export runs at the next scheduled time after creation.

## Managing Scheduled Exports

### Viewing All Schedules

1. Go to **Workspace Settings > Scheduled Exports**.
2. View a list of all active scheduled exports, including report name, frequency, last run time, and next run time.

### Editing a Schedule

1. In the scheduled exports list, click the **Edit** icon next to the schedule.
2. Modify frequency, recipients, format, or filters.
3. Click **Save**.

Changes take effect starting from the next scheduled run.

### Pausing and Resuming

To temporarily stop a scheduled export without deleting it:

1. Click the **Pause** icon next to the schedule.
2. The schedule status changes to **Paused** and no further exports are generated.
3. To resume, click the **Resume** icon.

### Deleting a Schedule

1. Click the **Delete** icon next to the schedule.
2. Confirm the deletion.

Deleting a schedule does not delete previously generated and delivered reports.

## Report Date Range Behavior

Scheduled exports use a rolling date range relative to the export date:

- **Daily exports**: Cover the previous 24 hours.
- **Weekly exports**: Cover the previous 7 days (ending at the export time).
- **Monthly exports**: Cover the previous calendar month.

If you configured a custom date range when setting up the report, the scheduled export overrides it with the rolling range appropriate for the frequency.

## Delivery and Storage

- Exports are delivered as email attachments. PDF files include the rendered report with charts and tables. CSV files contain raw tabular data.
- Each export email includes a download link valid for 30 days, in case the attachment is stripped by the recipient's email gateway.
- Taskmoor retains the last 90 days of export history. You can download past exports from **Workspace Settings > Scheduled Exports > History**.

## Security Considerations

- Reports contain workspace data and are sent via email. Ensure recipients are authorized to view the data.
- Exported PDFs do not include interactive elements but preserve all visible data at the time of generation.
- For compliance-sensitive environments, consider restricting recipients to internal email domains using domain verification.

## Troubleshooting

### RPT_ERR_TIMEOUT on Scheduled Exports

If a scheduled export fails with RPT_ERR_TIMEOUT, the report query exceeded the 60-second timeout for background exports. This typically happens with workspace-wide reports covering long date ranges. To fix:

- Edit the schedule and narrow the report scope to fewer projects.
- Reduce the date range by using a more frequent export schedule (e.g., weekly instead of monthly).

Failed exports are logged in the export history with the error code. Taskmoor retries once automatically 15 minutes after a failure.

### Recipients Not Receiving Exports

- Verify the email addresses are correct.
- Ask recipients to check spam or junk folders. Export emails are sent from `reports@mail.taskmoor.com`.
- If a recipient's email bounces three times consecutively, Taskmoor removes them from the schedule and notifies the schedule creator. Re-add the recipient after verifying their email.

## Related Articles

- Creating Dashboards
- Workload Reporting
- Time Tracking Reports
