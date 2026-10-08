---
doc_key: inc_2026_04_notification_delays
doc_type: known_incident
title: "Email Notification Delivery Delays"
product_areas:
  - notifications_email
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-04-17"
effective_from: "2026-04-10"
effective_to: "2026-04-10"
incident_status: resolved
started_at: "2026-04-10T06:00:00Z"
resolved_at: "2026-04-10T12:15:00Z"
affected_regions:
  - eu
  - apac
error_codes:
  - NOTIF_ERR_BOUNCE
last_update_at: "2026-04-10T12:15:00Z"
---

# Email Notification Delivery Delays

## Summary

Email notifications for task assignments, mentions, due-date reminders, and project updates experienced significant delivery delays in the EU and APAC regions. Some notifications bounced with `NOTIF_ERR_BOUNCE` errors. In-app notifications were unaffected.

## Timeline

**2026-04-10 06:00 UTC — Investigating**
Users in the EU and APAC regions reported missing or severely delayed email notifications. Monitoring confirmed a backlog in the email delivery queue for these regions.

**2026-04-10 07:30 UTC — Identified**
The root cause was traced to a DNS resolution failure for the outbound email relay servers in the EU and APAC regions. A scheduled DNS record update for the email sending infrastructure propagated incorrectly, causing the relay hosts to become unresolvable from the notification service.

**2026-04-10 09:00 UTC — Mitigation Applied**
DNS records were corrected and propagation was forced to the notification service's DNS resolvers. The email delivery queue began draining immediately.

**2026-04-10 12:15 UTC — Resolved**
All queued notifications were delivered. Bounce errors were caused by the relay timeout; no actual recipient-side bounces occurred. Email delivery latency returned to baseline.

## Root Cause

A DNS record update for outbound email relay servers propagated incorrectly, rendering the relay hosts unresolvable from the notification service in the EU and APAC regions. The notification service lacks a fallback relay configuration, amplifying the impact.

## Resolution

DNS records were corrected. A secondary fallback relay configuration was added to the notification service to provide redundancy for future DNS issues. DNS change validation was added to the email infrastructure deployment checklist.
