---
doc_key: inc_2026_08_webhook_delays
doc_type: known_incident
title: "Webhook Delivery Delays"
product_areas:
  - integrations_api
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-08-19"
effective_from: "2026-08-12"
effective_to: "2026-08-12"
incident_status: resolved
started_at: "2026-08-12T10:00:00Z"
resolved_at: "2026-08-12T18:30:00Z"
affected_regions:
  - us
  - eu
error_codes:
  - HOOK_ERR_TIMEOUT
last_update_at: "2026-08-12T18:30:00Z"
---

# Webhook Delivery Delays

## Summary

Webhook deliveries in the US and EU regions experienced significant delays, with many deliveries timing out and returning `HOOK_ERR_TIMEOUT` errors. Customers relying on webhook integrations for task updates, project events, and automation triggers were affected.

## Timeline

**2026-08-12 10:00 UTC — Investigating**
Monitoring detected a sharp increase in webhook delivery failures. The webhook delivery queue depth grew from a normal baseline of approximately 200 pending deliveries to over 45,000 within 30 minutes.

**2026-08-12 11:30 UTC — Identified**
Root cause identified as a misconfigured connection pool in the webhook delivery workers. A configuration change deployed at 09:45 UTC reduced the maximum concurrent outbound connections from 500 to 50 per worker node, creating a severe bottleneck.

**2026-08-12 13:00 UTC — Mitigation Applied**
The connection pool configuration was corrected and deployed to all webhook worker nodes. Queue processing resumed at normal throughput.

**2026-08-12 18:30 UTC — Resolved**
The delivery backlog was fully cleared. All queued webhooks were delivered successfully. Post-incident analysis confirmed no webhook events were lost; all were delivered with delay.

## Root Cause

A routine configuration update to the webhook delivery infrastructure inadvertently reduced the outbound connection pool limit. The change was part of a broader connection-management improvement initiative but was applied with incorrect parameter values.

## Resolution

The connection pool limit was restored to the correct value. A configuration validation step was added to the deployment pipeline for webhook infrastructure changes. Automated alerts were also added to trigger when queue depth exceeds 1,000 pending deliveries.
