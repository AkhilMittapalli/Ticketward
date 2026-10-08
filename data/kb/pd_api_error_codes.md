---
doc_key: pd_api_error_codes
doc_type: product_doc
title: "Complete API Error Codes Reference"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-19"
effective_from: "2026-06-22"
effective_to: null
---

## Overview

Taskmoor REST API v2 returns structured error responses with machine-readable error codes, human-readable messages, and HTTP status codes. Every error response follows a consistent envelope format. This reference documents all error codes across the API surface.

## Error Response Format

All errors are returned as JSON with the following structure:

```json
{
  "error": {
    "code": "API_ERR_401",
    "message": "Invalid or revoked API token.",
    "details": {},
    "request_id": "req_01HXYZ789"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Machine-readable error code |
| `message` | string | Human-readable description |
| `details` | object | Additional context (varies by error) |
| `request_id` | string | Unique request identifier for support reference |

## Authentication and Authorization Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `API_ERR_401` | 401 | Invalid or revoked API token | Verify the token is correct and has not been revoked. Regenerate in Settings > API > Tokens. |
| `API_ERR_403` | 403 | Insufficient scope or permission | Check the token's scopes match the requested resource. |

Example `401` response:

```json
{
  "error": {
    "code": "API_ERR_401",
    "message": "Invalid or revoked API token. Generate a new token in Settings > API > Tokens.",
    "request_id": "req_01A1B2C3"
  }
}
```

## Rate Limiting Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `API_ERR_429` | 429 | Rate limit exceeded | Wait for the duration specified in `retry_after` before retrying. Consider upgrading your plan for higher limits. |

The response includes the number of seconds before the limit resets:

```json
{
  "error": {
    "code": "API_ERR_429",
    "message": "Rate limit exceeded. Retry after 8 seconds.",
    "retry_after": 8,
    "request_id": "req_01D4E5F6"
  }
}
```

## Webhook Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `HOOK_ERR_TIMEOUT` | 504 | Webhook endpoint did not respond within 10 seconds | Optimize your endpoint to acknowledge receipt quickly; process payloads asynchronously. |
| `HOOK_ERR_410` | 410 | Webhook endpoint returned HTTP 410 Gone | The endpoint is permanently unavailable. Re-register the webhook with a valid URL. |

## SCIM Provisioning Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `SCIM_ERR_409` | 409 | User already exists in the workspace | The `userName` matches an existing account. Use PATCH to update the existing user. |
| `SCIM_ERR_422` | 422 | Invalid attribute mapping | Verify the SCIM payload includes required attributes (`userName`, `emails`) in the correct format. |

Example `409` response:

```json
{
  "error": {
    "code": "SCIM_ERR_409",
    "message": "A user with email jdoe@example.com already exists in this workspace.",
    "details": {
      "existing_user_id": "usr_001",
      "conflicting_field": "userName"
    },
    "request_id": "req_01G7H8I9"
  }
}
```

## SSO / SAML Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `SAML_ERR_302` | 401 | SAML assertion signature is invalid | Verify the IdP certificate is correctly configured in Taskmoor SSO settings. |
| `SAML_ERR_401` | 403 | User is not assigned to the Taskmoor application in the IdP | Assign the user to the Taskmoor app in your identity provider. |
| `SAML_ERR_408` | 401 | SAML assertion has expired | Check clock synchronization between the IdP and client. Assertions must be used within 5 minutes. |
| `SAML_ERR_415` | 422 | Unsupported NameID format | Taskmoor requires `emailAddress` NameID format. Update the IdP configuration. |

## Resource Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `TASK_ERR_DEP_CYCLE` | 409 | Adding this dependency would create a circular dependency chain | Review the dependency graph and remove conflicting dependencies before adding the new one. |
| `BOARD_ERR_RENDER` | 500 | Board failed to load due to rendering error | Retry the request. If the error persists, contact support with the `request_id`. |

## Automation Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `AUTO_ERR_LOOP` | 409 | An automation loop was detected and halted | Review your automation rules for circular triggers (e.g., Rule A triggers Rule B which triggers Rule A). |
| `AUTO_ERR_LIMIT` | 429 | Monthly automation run limit reached | Upgrade to Enterprise for unlimited automation runs, or wait for the limit to reset at the start of the next billing cycle. |

## Data Import/Export Errors

| Code | HTTP Status | Description | Resolution |
|------|:-----------:|-------------|------------|
| `IMP_ERR_ENCODING` | 422 | File uses an unsupported character encoding | Re-save the file as UTF-8 and retry the import. |
| `IMP_ERR_ROWS` | 422 | Import file exceeds the maximum row limit | Split the file into smaller batches. The limit is 50,000 rows per import. |
| `EXP_ERR_SIZE` | 422 | Export exceeds the maximum file size | Apply filters to reduce the export size, or use incremental exports with date ranges. |

## Server Errors

| HTTP Status | Description | Resolution |
|:-----------:|-------------|------------|
| 500 | Internal server error | Retry the request. If the error persists, contact support with the `request_id`. |
| 502 | Bad gateway | Temporary infrastructure issue. Retry after a brief delay. |
| 503 | Service unavailable | Taskmoor is undergoing maintenance. Check status.taskmoor.com for updates. |
| 504 | Gateway timeout | The request took too long to process. Reduce the scope of the query or retry. |

## Using `request_id` for Support

Every error response includes a `request_id`. When contacting Taskmoor support, provide this identifier along with the timestamp and error code to expedite investigation.
