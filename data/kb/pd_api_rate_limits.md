---
doc_key: pd_api_rate_limits
doc_type: product_doc
title: "API Rate Limits and Quotas by Plan"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-12"
effective_from: "2026-06-15"
effective_to: null
---

## Overview

Taskmoor enforces per-workspace rate limits on all REST API v2 endpoints to ensure platform stability and fair usage across customers. Rate limits are applied on a per-API-token basis and vary by subscription plan. The Free plan does not include API access.

## Rate Limit Tiers

| Plan | Requests per Minute | Burst Allowance | Daily Maximum |
|------|--------------------:|----------------:|--------------:|
| Free | No API access | N/A | N/A |
| Starter | 300 | 50 | 100,000 |
| Business | 600 | 100 | 500,000 |
| Enterprise | 1,200 | 200 | Unlimited |

The burst allowance permits short spikes above the per-minute rate for up to 10 seconds. Once the burst window closes, the standard rate limit applies.

## Rate Limit Headers

Every API response includes headers that communicate your current rate limit status:

```
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 587
X-RateLimit-Reset: 1719504000
X-RateLimit-Burst-Remaining: 98
```

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed per minute for this token |
| `X-RateLimit-Remaining` | Requests remaining in the current window |
| `X-RateLimit-Reset` | Unix timestamp when the current window resets |
| `X-RateLimit-Burst-Remaining` | Remaining burst capacity |

## Exceeding Rate Limits

When a request exceeds the rate limit, Taskmoor returns HTTP status `429 Too Many Requests` with error code `API_ERR_429`:

```json
{
  "error": {
    "code": "API_ERR_429",
    "message": "Rate limit exceeded. Retry after 12 seconds.",
    "retry_after": 12
  }
}
```

The `Retry-After` header is also included in the HTTP response with the number of seconds to wait before retrying.

### Checking Your Current Rate Limit Usage

```bash
curl -s -o /dev/null -D - \
  -H "Authorization: Bearer tm_test_abc123def456" \
  https://api.taskmoor.com/v2/tasks?limit=1
```

This returns only the headers, allowing you to inspect your remaining quota without consuming a meaningful request.

## Best Practices for Staying Within Limits

### Implement Exponential Backoff

When you receive a `429` response, wait the number of seconds indicated in `retry_after`, then retry. If successive retries also fail, apply exponential backoff with jitter:

```python
import time
import random

def retry_with_backoff(func, max_retries=5):
    for attempt in range(max_retries):
        response = func()
        if response.status_code != 429:
            return response
        wait = min(2 ** attempt + random.uniform(0, 1), 60)
        time.sleep(wait)
    raise Exception("Max retries exceeded")
```

### Use Bulk Endpoints

Instead of making individual requests for each resource, use bulk operations where available. For example, updating multiple tasks:

```bash
curl -X PATCH https://api.taskmoor.com/v2/tasks/bulk \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": ["task_01", "task_02", "task_03"],
    "updates": {
      "status": "in_progress"
    }
  }'
```

### Cache Responses

Taskmoor includes `ETag` headers on GET responses. Use conditional requests with `If-None-Match` to avoid consuming rate limit quota when data has not changed:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  -H "If-None-Match: \"a1b2c3d4\"" \
  https://api.taskmoor.com/v2/projects/proj_001
```

If the data is unchanged, Taskmoor returns `304 Not Modified` with no body, and the request counts at a reduced rate (one-fifth of a normal request).

## Webhook Delivery and Rate Limits

Webhook deliveries from Taskmoor to your endpoint are not counted against your API rate limit. However, if your webhook handler makes API calls back to Taskmoor, those calls are subject to the standard rate limits for your plan.

## Monitoring Usage

Workspace administrators can view API usage metrics in the Taskmoor dashboard under **Settings > API > Usage**. The dashboard shows:

- Requests per minute over the last 24 hours
- Daily request totals for the current billing period
- Top endpoints by request volume
- Rate limit violations count

Enterprise customers can also export usage data via the `/v2/usage/api` endpoint for integration with external monitoring tools.

## Plan Upgrade for Higher Limits

If your integration consistently approaches the rate limit ceiling, consider upgrading your plan. Enterprise customers with sustained high-volume needs can contact Taskmoor support to discuss custom rate limit arrangements beyond the standard 1,200 requests per minute.
