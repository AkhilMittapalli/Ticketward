---
doc_key: inc_2026_10_api_latency
doc_type: known_incident
title: "US Region API Latency Spike"
product_areas:
  - integrations_api
  - platform_availability
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-10-14"
effective_from: "2026-10-05"
effective_to: null
incident_status: investigating
started_at: "2026-10-05T16:20:00Z"
resolved_at: null
affected_regions:
  - us
error_codes:
  - API_ERR_429
  - PLAT_ERR_504
last_update_at: "2026-10-06T09:15:00Z"
---

# US Region API Latency Spike

## Summary

The Taskmoor REST API in the US region is experiencing elevated response latencies and an increase in `504` gateway timeout errors and `429` rate-limit responses. API consumers report response times of 3-8 seconds for endpoints that normally respond in under 200 milliseconds. The issue primarily affects the `/v2/tasks`, `/v2/projects`, and `/v2/webhooks` endpoint families.

## Impact

- Average API response latency in the US region has increased from 150ms to approximately 4,200ms.
- `PLAT_ERR_504` gateway timeout errors have increased by 340% relative to the preceding 7-day average.
- `API_ERR_429` rate-limit responses are being returned more frequently as the system applies back-pressure to protect downstream services.
- Customers relying on API integrations (Zapier, custom integrations, CI/CD pipelines) may experience delayed or failed operations.
- The Taskmoor web application and mobile apps use the same API layer and may exhibit slower load times for US-based users.

## Timeline

**2026-10-05 16:20 UTC — Investigating**
Automated latency monitoring triggered an alert when p95 response times exceeded 2,000ms on the US API cluster. The on-call platform team began investigation. Initial observations show elevated CPU utilization on the primary database read replicas serving the US region.

**2026-10-06 09:15 UTC — Update**
The investigation has narrowed the issue to a combination of factors: a recently deployed query optimization for project timeline aggregation appears to have introduced an inefficient query plan on projects with more than 500 tasks. This is compounded by a 40% increase in API traffic from a large enterprise customer's newly deployed integration. The engineering team is evaluating a rollback of the query change and temporary scaling adjustments to the read replica pool.

## Current Status

The incident remains under **active investigation**. The engineering team is testing a query plan rollback in the staging environment and preparing additional read replica capacity.

## Workarounds

- API consumers experiencing `429` responses should implement exponential backoff with jitter in their retry logic.
- For time-sensitive integrations, consider reducing the polling frequency temporarily or batching requests where the API supports it.
- The `/v2/tasks` endpoint supports a `fields` query parameter to request only needed fields, which can reduce response payload size and latency.
- Webhook-based integrations are less affected than polling-based ones; consider switching to webhooks where applicable.

## Next Steps

- Complete staging validation of query plan rollback (estimated: 2026-10-06 14:00 UTC).
- Deploy additional read replica capacity to the US region.
- Engage with the enterprise customer whose integration traffic spike contributed to the issue to discuss rate-limit adjustments.
