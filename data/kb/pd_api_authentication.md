---
doc_key: pd_api_authentication
doc_type: product_doc
title: "API Authentication: Tokens, Scopes, and Rotation"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-17"
effective_from: "2026-06-20"
effective_to: null
---

## Overview

Taskmoor REST API v2 uses bearer token authentication for all requests. API tokens are workspace-scoped and must be included in the `Authorization` header of every request. The Free plan does not include API access.

## Token Types

Taskmoor issues two types of API tokens, distinguished by their prefix:

| Token Type | Prefix | Purpose |
|------------|--------|---------|
| Production | `tm_live_` | Live workspace data; used in production integrations |
| Sandbox | `tm_test_` | Test environment; safe for development and CI pipelines |

Sandbox tokens operate against a separate data partition and do not affect production data. All code examples in Taskmoor documentation use `tm_test_` tokens.

## Creating an API Token

1. Navigate to **Settings > API > Tokens** in the Taskmoor workspace admin panel.
2. Click **Generate Token**.
3. Provide a descriptive name (e.g., "CI Pipeline Token").
4. Select the scopes required for your integration.
5. Click **Create**. The token is displayed once; copy and store it in a secrets manager.

### Programmatic Token Management

Workspace administrators can manage tokens via the API:

```bash
curl -X POST https://api.taskmoor.com/v2/tokens \
  -H "Authorization: Bearer tm_test_admin_token_001" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GitHub Actions Token",
    "scopes": ["tasks:read", "tasks:write", "projects:read"],
    "expires_in_days": 90
  }'
```

Response:

```json
{
  "id": "tok_01XYZ",
  "name": "GitHub Actions Token",
  "token": "tm_test_ghact_9f8e7d6c5b4a",
  "scopes": ["tasks:read", "tasks:write", "projects:read"],
  "expires_at": "2026-09-18T00:00:00Z",
  "created_at": "2026-06-20T10:15:00Z"
}
```

## Token Scopes

Scopes control which API resources a token can access. Use the principle of least privilege and assign only the scopes your integration requires.

| Scope | Permission | Description |
|-------|-----------|-------------|
| `tasks:read` | Read | List and retrieve tasks |
| `tasks:write` | Write | Create, update, and delete tasks |
| `projects:read` | Read | List and retrieve projects |
| `projects:write` | Write | Create, update, and delete projects |
| `boards:read` | Read | List and retrieve boards |
| `boards:write` | Write | Create, update, and delete boards |
| `comments:read` | Read | List and retrieve comments |
| `comments:write` | Write | Create and delete comments |
| `users:read` | Read | List workspace members |
| `users:write` | Write | Invite and manage workspace members |
| `webhooks:manage` | Admin | Create, update, and delete webhooks |
| `exports:read` | Read | Trigger and download exports |
| `time_entries:read` | Read | List and retrieve time entries |
| `time_entries:write` | Write | Create and update time entries |
| `admin` | Admin | Full workspace administration |

## Making Authenticated Requests

Include the token in the `Authorization` header using the `Bearer` scheme:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  https://api.taskmoor.com/v2/tasks
```

### Authentication Errors

If the token is missing, invalid, or has been revoked, the API returns HTTP `401`:

```json
{
  "error": {
    "code": "API_ERR_401",
    "message": "Invalid or revoked API token. Generate a new token in Settings > API > Tokens."
  }
}
```

If the token lacks the required scope for the requested resource, the API returns HTTP `403`:

```json
{
  "error": {
    "code": "API_ERR_403",
    "message": "Token does not have the required scope: tasks:write"
  }
}
```

## Token Rotation

Taskmoor supports zero-downtime token rotation. When you rotate a token, the old token remains valid for a grace period of 24 hours, during which both old and new tokens are accepted.

```bash
curl -X POST https://api.taskmoor.com/v2/tokens/tok_01XYZ/rotate \
  -H "Authorization: Bearer tm_test_admin_token_001"
```

Response:

```json
{
  "id": "tok_01XYZ",
  "new_token": "tm_test_rotated_1a2b3c4d5e",
  "old_token_expires_at": "2026-06-21T10:15:00Z",
  "created_at": "2026-06-20T10:15:00Z"
}
```

Update your integration to use the new token within the 24-hour grace window.

## Token Expiration

Tokens can be created with an explicit expiration date using the `expires_in_days` parameter. Tokens without an expiration date remain valid until revoked. Taskmoor sends an email notification to workspace administrators 14 days and 3 days before a token expires.

## Revoking Tokens

Revoke a token immediately by sending a DELETE request:

```bash
curl -X DELETE https://api.taskmoor.com/v2/tokens/tok_01XYZ \
  -H "Authorization: Bearer tm_test_admin_token_001"
```

Revoked tokens return `API_ERR_401` on all subsequent requests. Revocation is immediate and cannot be undone.

## Security Recommendations

- Store tokens in environment variables or a secrets manager; never commit them to source control.
- Use sandbox tokens (`tm_test_`) during development and CI testing.
- Set expiration dates on production tokens and rotate them at least every 90 days.
- Assign the minimum scopes required for each integration.
- Monitor token usage in **Settings > API > Usage** to detect unauthorized access.
