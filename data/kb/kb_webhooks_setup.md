---
doc_key: kb_webhooks_setup
doc_type: help_article
title: "Setting Up Webhooks"
product_areas:
  - integrations_api
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

Webhooks in Taskmoor allow your workspace to send real-time HTTP POST notifications to an external URL whenever specific events occur. This enables integrations with third-party services, custom dashboards, and automated workflows without polling the API.

Webhooks are available on the **Business** and **Enterprise** plans.

## Prerequisites

- You must be a **Workspace Owner** or **Admin** to create and manage webhooks.
- Your workspace must be on the Business or Enterprise plan.
- You need an HTTPS endpoint (URL) that can receive POST requests. HTTP (non-secure) endpoints are not supported.

## Creating a Webhook

1. Log in to Taskmoor as a Workspace Owner or Admin.
2. Navigate to **Settings > Integrations > Webhooks**.
3. Click **Add Webhook**.
4. Configure the webhook:
   - **Name**: A descriptive name (e.g., "Slack Notifications", "Data Warehouse Sync").
   - **Endpoint URL**: The HTTPS URL that will receive webhook payloads.
   - **Events**: Select one or more events to trigger the webhook:
     - `task.created` -- A new task is created.
     - `task.updated` -- A task is modified (status, assignee, due date, etc.).
     - `task.completed` -- A task is marked as complete.
     - `task.deleted` -- A task is deleted.
     - `project.created` -- A new project is created.
     - `project.archived` -- A project is archived.
     - `member.added` -- A new member joins the workspace.
     - `member.removed` -- A member is removed from the workspace.
     - `comment.created` -- A comment is added to a task.
   - **Secret** (optional but recommended): Enter a shared secret string. Taskmoor includes an HMAC-SHA256 signature in the `X-Taskmoor-Signature` header of each request, computed using this secret. Your endpoint can verify the signature to confirm the request originated from Taskmoor.
5. Click **Save Webhook**.

## Webhook Payload Format

Webhook payloads are sent as JSON in the body of an HTTP POST request. Each payload includes:

```json
{
  "event": "task.updated",
  "timestamp": "2026-08-15T14:30:00Z",
  "workspace_id": "ws_abc123",
  "data": {
    "task_id": "tsk_xyz789",
    "project_id": "prj_def456",
    "changes": {
      "status": {"from": "in_progress", "to": "completed"},
      "completed_by": "user@example.com"
    }
  }
}
```

### Headers

| Header | Description |
|---|---|
| `Content-Type` | `application/json` |
| `X-Taskmoor-Event` | The event type (e.g., `task.updated`) |
| `X-Taskmoor-Signature` | HMAC-SHA256 signature (if a secret is configured) |
| `X-Taskmoor-Delivery` | Unique delivery ID for this webhook call |

## Verifying Webhook Signatures

If you configured a webhook secret, verify the signature on your endpoint:

1. Read the raw request body (do not parse it first).
2. Compute the HMAC-SHA256 hash of the raw body using your webhook secret as the key.
3. Compare the computed hash with the value in the `X-Taskmoor-Signature` header.
4. If they match, the request is authentic. If not, reject the request.

## Retry Policy

If your endpoint returns an HTTP status code outside the 2xx range, Taskmoor retries the delivery:

- **Retry schedule**: 1 minute, 5 minutes, 30 minutes, 2 hours, 12 hours (5 retries total).
- After all retries are exhausted, the delivery is marked as failed.
- If a webhook endpoint fails consistently (10 consecutive deliveries), Taskmoor automatically disables the webhook and sends an email notification to the Workspace Owner.

## Managing Webhooks

### Viewing Webhook Activity

1. Go to **Settings > Integrations > Webhooks**.
2. Click on a webhook to view its details.
3. The **Recent Deliveries** tab shows:
   - Delivery timestamp
   - Event type
   - HTTP response code from your endpoint
   - Delivery status (Delivered, Retrying, Failed)

### Editing a Webhook

1. Go to **Settings > Integrations > Webhooks**.
2. Click the webhook name.
3. Click **Edit**.
4. Modify the name, endpoint URL, events, or secret.
5. Click **Save**.

### Disabling a Webhook

1. Find the webhook in the list.
2. Toggle the **Active** switch to off.
3. The webhook stops sending events but its configuration is preserved. Re-enable it at any time by toggling the switch back on.

### Deleting a Webhook

1. Click the webhook name.
2. Click **Delete Webhook**.
3. Confirm the deletion. This action is permanent.

## Troubleshooting

### HOOK_ERR_TIMEOUT

Your endpoint did not respond within 10 seconds. Taskmoor expects a response within this window. Optimize your endpoint to respond quickly, or have it acknowledge the request immediately and process the data asynchronously.

### HOOK_ERR_410

Your endpoint returned HTTP 410 (Gone), indicating it no longer exists. Taskmoor permanently disables the webhook. Update the endpoint URL or create a new webhook pointing to the correct URL.

### Webhook was automatically disabled

Taskmoor disables webhooks after 10 consecutive failed deliveries. Check your endpoint for availability issues, correct the problem, then re-enable the webhook from the webhooks settings page.

### Duplicate deliveries

In rare cases, network issues may cause duplicate deliveries. Use the `X-Taskmoor-Delivery` header to deduplicate events on your endpoint by tracking processed delivery IDs.
