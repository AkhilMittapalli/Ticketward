---
doc_key: kb_audit_log
doc_type: help_article
title: "Using the Audit Log"
product_areas:
  - user_admin_permissions
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

The audit log in Taskmoor provides a detailed, immutable record of significant actions taken within your workspace. It is designed for compliance, security investigations, and operational transparency. The audit log captures who did what, when, and from where across your workspace.

The audit log is available exclusively on the **Enterprise** plan.

## Prerequisites

- You must be a **Workspace Owner** or **Admin** to access the audit log.
- Your workspace must be on the Enterprise plan.

## Accessing the Audit Log

1. Log in to Taskmoor as a Workspace Owner or Admin.
2. Navigate to **Settings > Security > Audit Log**.
3. The audit log displays events in reverse chronological order (most recent first).

## Events Captured

The audit log records the following categories of events:

### Authentication Events

- User login (successful and failed attempts)
- Password resets
- 2FA enablement and disablement
- SSO login events
- Account lockouts (AUTH_ERR_LOCKED)

### Member Management

- Member invitations sent, accepted, and revoked
- Role changes
- Member deactivation and reactivation
- Guest access changes
- SCIM provisioning events

### Security Settings

- SSO configuration changes
- Domain verification
- 2FA enforcement changes
- API token creation and revocation
- Webhook creation, modification, and deletion

### Workspace Settings

- Plan changes (upgrades and downgrades)
- Billing updates
- Integration connections and disconnections
- Automation rule changes
- Workspace export requests

### Project and Data Events

- Project creation, archival, and deletion
- Workspace data exports
- Bulk operations (bulk task updates, bulk member changes)

## Filtering and Searching

### Basic Filters

Use the filter bar at the top of the audit log to narrow results:

- **Date Range**: Select a start and end date. The audit log retains data for 365 days.
- **Actor**: Filter by the user who performed the action.
- **Event Type**: Filter by category (Authentication, Member Management, Security, etc.).
- **IP Address**: Filter events from a specific IP address.

### Search

Use the search bar to look for specific terms within event descriptions. For example, searching for an email address shows all events related to that user.

## Reading Audit Log Entries

Each audit log entry contains:

| Field | Description |
|---|---|
| Timestamp | The date and time (UTC) of the event |
| Actor | The user who performed the action (email and name) |
| Event Type | The category and specific action |
| Description | A human-readable summary of what happened |
| IP Address | The IP address from which the action was performed |
| User Agent | The browser or API client used |
| Target | The resource affected (user, project, setting, etc.) |
| Result | Whether the action succeeded or failed |

## Exporting the Audit Log

To export audit log data for compliance or analysis:

1. Apply any filters to narrow the data you want to export.
2. Click **Export** in the top-right corner.
3. Choose the format: **CSV** or **JSON**.
4. Click **Download**.

The export includes all filtered entries with their full details. Exports are limited to 50,000 entries per download. For larger datasets, narrow the date range and export in batches.

### Scheduled Exports

Enterprise workspaces can configure scheduled report exports, including audit log data:

1. Go to **Settings > Security > Audit Log**.
2. Click **Schedule Export**.
3. Set the frequency (daily, weekly, or monthly).
4. Choose the format (CSV or JSON).
5. Enter the email address(es) to receive the export.
6. Click **Save Schedule**.

## Retention

- Audit log data is retained for **365 days** from the event date.
- After 365 days, events are permanently removed and cannot be recovered.
- To retain data beyond 365 days, set up scheduled exports to your own storage.

## Use Cases

### Investigating a Security Incident

If you suspect unauthorized access:

1. Filter by **Authentication** events and the suspected time frame.
2. Look for failed login attempts (AUTH_ERR_LOCKED events) or logins from unusual IP addresses.
3. Cross-reference with member management events to check if roles were changed.
4. Export the relevant entries for your security team.

### Compliance Auditing

For SOC 2 or similar compliance requirements:

1. Set up scheduled weekly exports of the full audit log.
2. Filter by Security Settings events to document all configuration changes.
3. Use the Actor filter to verify that only authorized personnel made sensitive changes.

### Troubleshooting Permission Issues

If a user reports losing access (PERM_ERR_403):

1. Filter the audit log by the user's email address.
2. Look for recent role change or project removal events.
3. Identify who made the change and when.

## Troubleshooting

### Audit log shows "No events found"

- Verify your date range includes the period you are investigating.
- Clear any active filters that may be hiding events.
- Events from before your workspace upgraded to Enterprise are not retroactively logged.

### Export fails or is empty

- Ensure the filtered result set is not empty before exporting.
- If the export exceeds 50,000 entries, narrow the date range and try again.
- Check that your browser allows downloads from Taskmoor's domain.
