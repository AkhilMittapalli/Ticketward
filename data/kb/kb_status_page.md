---
doc_key: kb_status_page
doc_type: help_article
title: "Understanding the Taskmoor Status Page"
product_areas:
  - platform_availability
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

The Taskmoor status page provides real-time information about platform availability, ongoing incidents, scheduled maintenance, and historical uptime. It is publicly accessible and does not require a Taskmoor account. All plan holders can use the status page to check service health before reporting issues to support.

## Accessing the Status Page

Visit the status page at **status.taskmoor.com** from any browser. No login is required.

## Status Page Components

### Overall Status Banner

At the top of the page, a banner displays the current overall system status:

- **All Systems Operational** (green) -- All services are functioning normally.
- **Partial Outage** (yellow) -- One or more non-critical services are degraded.
- **Major Outage** (red) -- Core services are down or severely impacted.
- **Under Maintenance** (blue) -- Scheduled maintenance is in progress.

### Service Components

Below the banner, individual service components are listed with their current status:

| Component | Description |
|---|---|
| **Web Application** | The main Taskmoor web interface |
| **API** | REST API v2 endpoints |
| **Mobile Apps** | iOS and Android app connectivity |
| **Desktop App** | Desktop application connectivity |
| **Real-time Updates** | WebSocket connections for live task updates |
| **Email Notifications** | Outbound email delivery (digest, alerts) |
| **Integrations** | Third-party integrations (Slack, GitHub, calendars) |
| **File Storage** | File upload and download services |
| **Search** | Workspace and task search functionality |

Each component shows one of four statuses: Operational, Degraded Performance, Partial Outage, or Major Outage.

### Regional Status

Taskmoor operates in three regions: **US**, **EU**, and **APAC**. The status page shows per-region health for each component. If an incident affects only one region, the other regions may remain operational.

To check your region, go to **Workspace Settings > General** in your Taskmoor account. Your region is displayed under **Data Region**.

## Incidents

### Active Incidents

Active incidents appear at the top of the status page with:

- **Title**: A short description of the issue (e.g., "Elevated API Error Rates in EU Region").
- **Severity**: Minor, Major, or Critical.
- **Affected components**: Which services are impacted.
- **Timeline**: A chronological list of updates from the Taskmoor operations team, including when the issue was identified, what is being done, and estimated resolution time.

### Incident Updates

The operations team posts updates to active incidents as the situation evolves. Updates include:

- **Investigating**: The team is aware and actively investigating.
- **Identified**: The root cause has been found.
- **Monitoring**: A fix has been deployed and the team is monitoring for stability.
- **Resolved**: The incident is fully resolved and services are back to normal.

### Past Incidents

Scroll down on the status page to view past incidents from the last 90 days. Each entry shows the incident title, date, duration, and a summary of the root cause and resolution.

## Scheduled Maintenance

Upcoming scheduled maintenance windows appear in a dedicated section of the status page. Each entry includes:

- **Date and time** (displayed in your browser's local timezone).
- **Expected duration**.
- **Affected components**.
- **Description** of the maintenance activity.

Maintenance windows are announced at least 48 hours in advance. During maintenance, affected services may be temporarily unavailable.

## Subscribing to Status Updates

To receive notifications when Taskmoor's status changes:

1. On the status page, click **Subscribe to Updates**.
2. Choose your notification channel:
   - **Email** -- Enter your email address to receive incident and maintenance notifications.
   - **Slack** -- Connect a Slack webhook URL to post status updates to a Slack channel.
   - **RSS** -- Subscribe to the RSS feed for status updates.
3. Confirm your subscription.

You can unsubscribe at any time from the link in any status notification email.

## Common Error Codes and the Status Page

When you encounter platform error codes in Taskmoor, check the status page to determine if the issue is on Taskmoor's side:

| Error Code | What to Check |
|---|---|
| **PLAT_ERR_503** | Service Unavailable. Check the status page for an active outage. If no incident is posted, the issue may be temporary. Retry after 30 seconds. |
| **PLAT_ERR_504** | Gateway Timeout. Check the status page for degraded performance on the API or Web Application components. If performance is degraded, wait for the incident to resolve. If the status page shows all systems operational, the issue may be specific to your request (e.g., a very large query). |

## Using the Status Page During Outages

If you cannot access the Taskmoor web application:

1. Check **status.taskmoor.com** from your browser to confirm whether there is an active outage.
2. Subscribe to updates for real-time notifications on resolution progress.
3. If the status page shows all systems operational but you still cannot access Taskmoor, the issue may be on your end. Check your internet connection, VPN, or firewall settings.
4. Contact Taskmoor support if the issue persists and no incident is posted.

## API Status Endpoint

Developers can programmatically check Taskmoor's status via the API:

```
GET https://status.taskmoor.com/api/v1/status
```

This returns a JSON object with the current status of each component and any active incidents. No authentication is required.

## Related Articles

- Mobile Offline Mode
- Daily Digest Settings
- Calendar Sync with Google Calendar and Outlook Calendar
