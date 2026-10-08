---
doc_key: kb_rest_api_getting_started
doc_type: help_article
title: "Getting Started with REST API v2"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-12"
effective_from: "2026-06-15"
effective_to: null
---

## Overview

The Taskmoor REST API v2 allows you to programmatically access and manage your workspace data. You can create and update tasks, manage projects, retrieve reports, and integrate Taskmoor with other tools in your workflow. This article covers the basics of authenticating, making requests, and handling responses.

The REST API v2 is available on the **Starter**, **Business**, and **Enterprise** plans.

## Prerequisites

- Your workspace must be on the Starter, Business, or Enterprise plan.
- You need an API token. See the API tokens article for how to generate one.
- Basic familiarity with HTTP requests and JSON.

## Base URL

All API requests use the following base URL:

```
https://api.taskmoor.com/v2
```

Append the specific endpoint path to the base URL for each request.

## Authentication

Every API request must include your API token in the `Authorization` header:

```
Authorization: Bearer tm_live_your_token_here
```

Use `tm_live_` tokens for production requests and `tm_test_` tokens for development and testing against sandbox data.

Requests without a valid token receive error **API_ERR_401** (invalid token).

## Making Your First Request

### List Projects

Retrieve all projects in your workspace:

```
GET /v2/projects
Authorization: Bearer tm_live_your_token_here
```

**Response** (200 OK):

```json
{
  "data": [
    {
      "id": "prj_abc123",
      "name": "Website Redesign",
      "status": "active",
      "created_at": "2026-06-01T10:00:00Z"
    },
    {
      "id": "prj_def456",
      "name": "Q3 Marketing",
      "status": "active",
      "created_at": "2026-07-15T08:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total": 2
  }
}
```

### Create a Task

Create a new task in a project:

```
POST /v2/projects/prj_abc123/tasks
Authorization: Bearer tm_live_your_token_here
Content-Type: application/json

{
  "title": "Update landing page copy",
  "assignee_email": "jane@company.com",
  "due_date": "2026-09-01",
  "priority": "high",
  "description": "Review and update the hero section copy to match the new brand guidelines."
}
```

**Response** (201 Created):

```json
{
  "data": {
    "id": "tsk_xyz789",
    "title": "Update landing page copy",
    "status": "not_started",
    "assignee_email": "jane@company.com",
    "due_date": "2026-09-01",
    "priority": "high",
    "created_at": "2026-08-01T14:00:00Z"
  }
}
```

## Common Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/v2/projects` | List all projects |
| POST | `/v2/projects` | Create a project |
| GET | `/v2/projects/:id` | Get a specific project |
| GET | `/v2/projects/:id/tasks` | List tasks in a project |
| POST | `/v2/projects/:id/tasks` | Create a task |
| PATCH | `/v2/tasks/:id` | Update a task |
| DELETE | `/v2/tasks/:id` | Delete a task |
| GET | `/v2/users` | List workspace members |
| GET | `/v2/me` | Get the authenticated user |

## Pagination

List endpoints return paginated results. Use the `page` and `per_page` query parameters:

```
GET /v2/projects?page=2&per_page=50
```

The response includes a `pagination` object with `page`, `per_page`, and `total` fields. The maximum `per_page` value is 100.

## Error Handling

The API returns standard HTTP status codes and a JSON error body:

| Status Code | Error Code | Description |
|---|---|---|
| 401 | API_ERR_401 | Invalid or missing API token |
| 403 | PERM_ERR_403 | Authenticated user lacks permission for this action |
| 429 | API_ERR_429 | Rate limit exceeded |
| 404 | -- | Resource not found |
| 422 | -- | Validation error (check the `errors` array in the response) |

**Example error response** (429):

```json
{
  "error": {
    "code": "API_ERR_429",
    "message": "Rate limit exceeded. Try again in 12 seconds.",
    "retry_after": 12
  }
}
```

## Rate Limits

| Plan | Requests per Minute |
|---|---|
| Starter | 300 |
| Business | 600 |
| Enterprise | 1,200 |

When you hit the rate limit, the API returns **API_ERR_429** with a `Retry-After` header. Implement exponential backoff to handle rate limiting gracefully.

## Filtering and Sorting

Most list endpoints support filtering and sorting via query parameters:

```
GET /v2/projects/prj_abc123/tasks?status=in_progress&assignee=jane@company.com&sort=due_date&order=asc
```

Common filter parameters:
- `status`: Filter by task status (not_started, in_progress, completed).
- `assignee`: Filter by assignee email.
- `priority`: Filter by priority (low, medium, high, urgent).
- `due_date_from` / `due_date_to`: Filter by due date range.

## Webhooks vs. Polling

For real-time notifications, use webhooks (Business and Enterprise plans) instead of polling the API. Webhooks push data to your endpoint immediately when events occur, reducing API calls and latency. See the webhooks setup article for configuration details.

## Troubleshooting

### API_ERR_401

- Verify the token is included in the `Authorization` header.
- Check that the token prefix matches the environment: `tm_live_` for production, `tm_test_` for sandbox.
- Ensure the token has not been revoked.

### API_ERR_429

- You have exceeded your plan's rate limit. Wait for the duration specified in the `Retry-After` header.
- Review your integration to reduce unnecessary API calls (use pagination, cache responses, consolidate requests).

### PERM_ERR_403

- The API token's owner does not have permission to perform the requested action. Check the user's workspace and project roles.
