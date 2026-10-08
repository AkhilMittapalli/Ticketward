---
doc_key: pd_api_sandbox
doc_type: product_doc
title: "API Sandbox Environment for Testing"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-20"
effective_from: "2026-07-24"
effective_to: null
---

## Overview

Taskmoor provides a sandbox environment for developing and testing API integrations without affecting production workspace data. The sandbox mirrors production API behavior with isolated data partitions. Sandbox access is available on Starter, Business, and Enterprise plans.

## Sandbox vs. Production

| Feature | Sandbox | Production |
|---------|---------|------------|
| Token prefix | `tm_test_` | `tm_live_` |
| Base URL | `https://api.taskmoor.com/v2` | `https://api.taskmoor.com/v2` |
| Data isolation | Separate partition | Live workspace data |
| Rate limits | Same as plan | Same as plan |
| Webhooks | Delivered to registered endpoints | Delivered to registered endpoints |
| SCIM | Fully functional | Fully functional |
| Billing impact | None | Normal usage metering |

The sandbox and production environments share the same base URL. The API determines the environment from the token prefix: requests authenticated with `tm_test_` tokens operate on the sandbox partition, while `tm_live_` tokens access production data.

## Getting Started

### 1. Generate a Sandbox Token

Navigate to **Settings > API > Tokens** and click **Generate Token**. Select the **Sandbox** environment toggle before creating the token. The generated token will have the `tm_test_` prefix.

### 2. Make Your First Sandbox Request

```bash
curl -H "Authorization: Bearer tm_test_sandbox_abc123" \
  https://api.taskmoor.com/v2/projects
```

If the sandbox is empty, the response returns an empty collection:

```json
{
  "data": [],
  "pagination": {
    "cursor": null,
    "has_more": false,
    "total_count": 0
  }
}
```

### 3. Seed Test Data

Create test projects and tasks to populate the sandbox:

```bash
curl -X POST https://api.taskmoor.com/v2/projects \
  -H "Authorization: Bearer tm_test_sandbox_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Project Alpha",
    "description": "Sandbox project for integration testing."
  }'
```

```bash
curl -X POST https://api.taskmoor.com/v2/tasks \
  -H "Authorization: Bearer tm_test_sandbox_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test task 001",
    "project_id": "proj_test_001",
    "status": "todo",
    "priority": "medium"
  }'
```

## Sandbox Data Lifecycle

### Data Retention

Sandbox data is retained for 90 days from the last API activity on the sandbox partition. If no sandbox API calls are made for 90 consecutive days, the sandbox data is automatically purged.

### Data Reset

Reset all sandbox data to start fresh:

```bash
curl -X POST https://api.taskmoor.com/v2/sandbox/reset \
  -H "Authorization: Bearer tm_test_sandbox_abc123"
```

Response:

```json
{
  "status": "reset_complete",
  "message": "Sandbox data has been cleared. All test projects, tasks, and configurations have been removed.",
  "reset_at": "2026-07-24T12:00:00Z"
}
```

This operation is irreversible and deletes all sandbox data including projects, tasks, comments, webhooks, automation rules, and time entries.

## Testing Webhooks in Sandbox

Register a webhook with a sandbox token to test webhook deliveries:

```bash
curl -X POST https://api.taskmoor.com/v2/webhooks \
  -H "Authorization: Bearer tm_test_sandbox_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-dev-server.example.com/webhooks/test",
    "events": ["task.created", "task.updated"],
    "secret": "whsec_test_secret_123"
  }'
```

Sandbox webhooks are delivered to your registered endpoint identically to production webhooks, including HMAC signatures. This allows you to test your signature verification implementation before going live.

### Using Request Inspection Tools

For development, you can use request inspection services as your webhook URL. Taskmoor delivers sandbox webhooks to any HTTPS endpoint.

## Testing SCIM in Sandbox (Enterprise)

Sandbox supports full SCIM operations for testing provisioning flows:

```bash
curl -X POST https://api.taskmoor.com/scim/v2/Users \
  -H "Authorization: Bearer tm_test_scim_sandbox_456" \
  -H "Content-Type: application/scim+json" \
  -d '{
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
    "userName": "testuser@example.com",
    "name": {"givenName": "Test", "familyName": "User"},
    "emails": [{"value": "testuser@example.com", "primary": true}],
    "active": true
  }'
```

## Sandbox Limitations

| Limitation | Detail |
|-----------|--------|
| Export file size | Sandbox exports are capped at 100 MB regardless of plan |
| Scheduled exports | Not available in sandbox |
| Email notifications | Sandbox does not send email notifications for invitations or alerts |
| Integrations | Third-party integrations (Slack, GitHub, etc.) are not connected in sandbox |
| Audit log | Sandbox operations are not recorded in the production audit log |

## CI/CD Integration

Use sandbox tokens in automated test suites and CI pipelines:

```yaml
# Example GitHub Actions workflow
env:
  TASKMOOR_API_TOKEN: ${{ secrets.TASKMOOR_SANDBOX_TOKEN }}

steps:
  - name: Run integration tests
    run: |
      pytest tests/integrations/ \
        --taskmoor-token=$TASKMOOR_API_TOKEN \
        --taskmoor-base-url=https://api.taskmoor.com/v2
```

Before each test run, call the sandbox reset endpoint to ensure a clean test environment.

## Error Behavior

Sandbox returns the same error codes and response formats as production. All error codes documented in the API Error Codes Reference apply identically in the sandbox environment, including `API_ERR_401`, `API_ERR_429`, `SCIM_ERR_409`, and all others.

## Promoting to Production

When your integration is tested and ready, switch from a `tm_test_` token to a `tm_live_` token. No other code changes are needed; the API behaves identically in both environments.
