---
doc_key: pd_rest_api_reference
doc_type: product_doc
title: "REST API v2 Overview and Conventions"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-24"
effective_from: "2026-06-27"
effective_to: null
---

## Overview

The Taskmoor REST API v2 provides programmatic access to your workspace's projects, tasks, boards, comments, users, time entries, and more. All endpoints follow RESTful conventions and return JSON responses. API access is available on Starter, Business, and Enterprise plans.

## Base URL

All API requests are made to:

```
https://api.taskmoor.com/v2
```

Every endpoint path in this documentation is relative to this base. For example, the tasks endpoint is `https://api.taskmoor.com/v2/tasks`.

## Authentication

All requests require a bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  https://api.taskmoor.com/v2/tasks
```

Tokens use the prefix `tm_live_` for production and `tm_test_` for sandbox environments. See the API Authentication guide for details on token creation, scopes, and rotation.

## Request Format

### Content Type

All request bodies must be JSON with the `Content-Type: application/json` header:

```bash
curl -X POST https://api.taskmoor.com/v2/tasks \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{"title": "Review Q3 report", "project_id": "proj_001"}'
```

### HTTP Methods

| Method | Usage |
|--------|-------|
| `GET` | Retrieve a resource or list resources |
| `POST` | Create a new resource |
| `PATCH` | Partially update an existing resource |
| `PUT` | Replace an existing resource entirely |
| `DELETE` | Remove a resource |

## Response Format

All responses return JSON with the `Content-Type: application/json` header.

### Single Resource Response

```json
{
  "id": "task_042",
  "title": "Review Q3 report",
  "status": "todo",
  "project_id": "proj_001",
  "assignee_id": null,
  "created_at": "2026-06-27T09:00:00Z",
  "updated_at": "2026-06-27T09:00:00Z"
}
```

### Collection Response

Collection endpoints return paginated results:

```json
{
  "data": [
    {"id": "task_042", "title": "Review Q3 report"},
    {"id": "task_043", "title": "Update dashboard"}
  ],
  "pagination": {
    "cursor": "eyJpZCI6InRhc2tfMDQzIn0=",
    "has_more": true,
    "total_count": 148
  }
}
```

## Available Endpoints

| Endpoint | Methods | Description | Plan |
|----------|---------|-------------|------|
| `/v2/tasks` | GET, POST | List and create tasks | Starter+ |
| `/v2/tasks/{id}` | GET, PATCH, DELETE | Retrieve, update, delete a task | Starter+ |
| `/v2/projects` | GET, POST | List and create projects | Starter+ |
| `/v2/projects/{id}` | GET, PATCH, DELETE | Retrieve, update, delete a project | Starter+ |
| `/v2/boards` | GET, POST | List and create boards | Starter+ |
| `/v2/boards/{id}` | GET, PATCH, DELETE | Retrieve, update, delete a board | Starter+ |
| `/v2/comments` | GET, POST | List and create comments | Starter+ |
| `/v2/comments/{id}` | GET, DELETE | Retrieve or delete a comment | Starter+ |
| `/v2/users` | GET | List workspace users | Starter+ |
| `/v2/users/{id}` | GET | Retrieve a user | Starter+ |
| `/v2/webhooks` | GET, POST | List and create webhooks | Business+ |
| `/v2/webhooks/{id}` | GET, PATCH, DELETE | Manage a webhook | Business+ |
| `/v2/time-entries` | GET, POST | List and create time entries | Business+ |
| `/v2/time-entries/{id}` | GET, PATCH, DELETE | Manage a time entry | Business+ |
| `/v2/exports` | GET, POST | List and trigger exports | Business+ |

## Common Query Parameters

Most collection endpoints accept the following query parameters:

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `limit` | integer | 50 | Number of results per page (max: 100) |
| `cursor` | string | null | Pagination cursor from a previous response |
| `sort` | string | `created_at` | Field to sort by |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `created_after` | string | null | ISO 8601 timestamp filter |
| `created_before` | string | null | ISO 8601 timestamp filter |
| `updated_after` | string | null | ISO 8601 timestamp filter |

## HTTP Status Codes

| Status | Meaning |
|:------:|---------|
| 200 | Success |
| 201 | Resource created |
| 204 | Successful deletion (no body) |
| 400 | Malformed request |
| 401 | Authentication failed |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (e.g., dependency cycle) |
| 422 | Validation error |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 502 | Bad gateway |
| 503 | Service unavailable |
| 504 | Gateway timeout |

## Timestamps

All timestamps in requests and responses use ISO 8601 format with UTC timezone: `2026-06-27T09:00:00Z`. Taskmoor does not accept other timezone offsets in API requests.

## Idempotency

For `POST` requests, you can include an `Idempotency-Key` header to ensure the operation is performed at most once:

```bash
curl -X POST https://api.taskmoor.com/v2/tasks \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-request-id-001" \
  -d '{"title": "Idempotent task creation"}'
```

Idempotency keys are valid for 24 hours. Repeated requests with the same key return the original response without creating a duplicate resource.
