---
doc_key: pd_webhook_reference
doc_type: product_doc
title: "Webhook Events Reference and Payloads"
product_areas:
  - integrations_api
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-16"
effective_from: "2026-06-19"
effective_to: null
---

## Overview

Taskmoor webhooks allow your application to receive real-time HTTP POST notifications when events occur in your workspace. Webhooks are available on Business and Enterprise plans and are managed through the REST API v2.

## Registering a Webhook

Create a webhook subscription by sending a POST request to the `/v2/webhooks` endpoint:

```bash
curl -X POST https://api.taskmoor.com/v2/webhooks \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.example.com/webhooks/taskmoor",
    "events": ["task.created", "task.updated", "task.deleted"],
    "secret": "whsec_your_signing_secret",
    "active": true,
    "description": "Task sync webhook"
  }'
```

Response:

```json
{
  "id": "wh_01HXYZ",
  "url": "https://your-app.example.com/webhooks/taskmoor",
  "events": ["task.created", "task.updated", "task.deleted"],
  "active": true,
  "description": "Task sync webhook",
  "created_at": "2026-06-19T14:30:00Z"
}
```

### Webhook Registration Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `url` | string | Yes | HTTPS endpoint to receive webhook payloads |
| `events` | array | Yes | List of event types to subscribe to |
| `secret` | string | Yes | Shared secret for HMAC signature verification |
| `active` | boolean | No | Whether the webhook is active (default: `true`) |
| `description` | string | No | Human-readable label for the webhook |

## Webhook Payload Structure

All webhook payloads share a common envelope:

```json
{
  "id": "evt_01ABC",
  "type": "task.updated",
  "workspace_id": "ws_001",
  "timestamp": "2026-06-19T14:35:22Z",
  "data": {
    "task": {
      "id": "task_042",
      "title": "Update API documentation",
      "status": "in_progress",
      "assignee_id": "usr_007",
      "project_id": "proj_003",
      "updated_fields": ["status"],
      "previous_values": {
        "status": "todo"
      }
    }
  }
}
```

### Envelope Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique event identifier for idempotency |
| `type` | string | Event type (e.g., `task.created`) |
| `workspace_id` | string | Workspace where the event occurred |
| `timestamp` | string | ISO 8601 timestamp of the event |
| `data` | object | Event-specific payload |

## Listing Registered Webhooks

```bash
curl -X GET https://api.taskmoor.com/v2/webhooks \
  -H "Authorization: Bearer tm_test_abc123def456"
```

## Updating a Webhook

```bash
curl -X PATCH https://api.taskmoor.com/v2/webhooks/wh_01HXYZ \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "events": ["task.created", "task.updated", "task.deleted", "comment.created"],
    "active": true
  }'
```

## Deleting a Webhook

```bash
curl -X DELETE https://api.taskmoor.com/v2/webhooks/wh_01HXYZ \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content` on success.

## Delivery and Retry Policy

Taskmoor expects your endpoint to return a `2xx` status code within 10 seconds. If your endpoint does not respond in time, Taskmoor records a `HOOK_ERR_TIMEOUT` and retries the delivery.

The retry schedule uses exponential backoff:

| Attempt | Delay After Failure |
|:-------:|:-------------------:|
| 1 | 1 minute |
| 2 | 5 minutes |
| 3 | 30 minutes |
| 4 | 2 hours |
| 5 | 12 hours |

After five failed delivery attempts, the webhook is automatically deactivated. Workspace administrators receive an email notification when a webhook is disabled due to repeated failures.

If your endpoint returns HTTP `410 Gone`, Taskmoor records `HOOK_ERR_410` and immediately deactivates the webhook without retrying.

## Error Codes

| Error Code | Description | Action |
|------------|-------------|--------|
| `HOOK_ERR_TIMEOUT` | Endpoint did not respond within 10 seconds | Optimize endpoint response time; ensure it returns 200 before processing |
| `HOOK_ERR_410` | Endpoint returned 410 Gone | Webhook is deactivated; re-register if the endpoint is restored |

## Idempotency

Each webhook payload includes a unique event `id`. Your handler should store processed event IDs and skip duplicates to ensure idempotent processing, as retries may deliver the same event more than once.

## Testing Webhooks

Use the webhook test endpoint to send a sample payload to your registered URL:

```bash
curl -X POST https://api.taskmoor.com/v2/webhooks/wh_01HXYZ/test \
  -H "Authorization: Bearer tm_test_abc123def456"
```

This sends a `webhook.test` event with a synthetic payload to verify connectivity and signature validation.
