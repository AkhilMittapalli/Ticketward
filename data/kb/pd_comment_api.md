---
doc_key: pd_comment_api
doc_type: product_doc
title: "Comments API Endpoint Reference"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-12"
effective_from: "2026-07-16"
effective_to: null
---

## Overview

The Comments API allows you to create, retrieve, and delete comments on Taskmoor tasks. Comments support Markdown formatting and can include @mentions to notify other workspace members. This endpoint is available on Starter, Business, and Enterprise plans.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v2/comments` | List comments with filters |
| `POST` | `/v2/comments` | Create a comment on a task |
| `GET` | `/v2/comments/{comment_id}` | Retrieve a single comment |
| `DELETE` | `/v2/comments/{comment_id}` | Delete a comment |

## List Comments

Retrieve comments for a specific task:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/comments?task_id=task_042&sort=created_at&order=asc&limit=50"
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `task_id` | string | null | Filter by task (required unless `project_id` is provided) |
| `project_id` | string | null | Filter all comments within a project |
| `author_id` | string | null | Filter by comment author |
| `created_after` | string | null | Comments created after this ISO 8601 timestamp |
| `created_before` | string | null | Comments created before this ISO 8601 timestamp |
| `sort` | string | `created_at` | Sort field |
| `order` | string | `desc` | Sort order: `asc` or `desc` |
| `limit` | integer | 50 | Results per page (max: 100) |
| `cursor` | string | null | Pagination cursor |

### Response

```json
{
  "data": [
    {
      "id": "cmt_001",
      "task_id": "task_042",
      "author": {
        "id": "usr_007",
        "name": "Jordan Lee",
        "email": "jlee@example.com",
        "avatar_url": "https://cdn.taskmoor.com/avatars/usr_007.png"
      },
      "body": "I've completed the initial implementation. @usr_012 can you review the PR?",
      "body_html": "<p>I've completed the initial implementation. <span class=\"mention\" data-user=\"usr_012\">@Sam Rivera</span> can you review the PR?</p>",
      "mentions": ["usr_012"],
      "reactions": [
        {"emoji": "thumbsup", "count": 2, "users": ["usr_001", "usr_012"]}
      ],
      "created_at": "2026-07-16T10:30:00Z",
      "updated_at": "2026-07-16T10:30:00Z"
    },
    {
      "id": "cmt_002",
      "task_id": "task_042",
      "author": {
        "id": "usr_012",
        "name": "Sam Rivera",
        "email": "srivera@example.com",
        "avatar_url": "https://cdn.taskmoor.com/avatars/usr_012.png"
      },
      "body": "Reviewed and approved. Nice work on the error handling.",
      "body_html": "<p>Reviewed and approved. Nice work on the error handling.</p>",
      "mentions": [],
      "reactions": [],
      "parent_comment_id": null,
      "created_at": "2026-07-16T14:15:00Z",
      "updated_at": "2026-07-16T14:15:00Z"
    }
  ],
  "pagination": {
    "cursor": null,
    "has_more": false,
    "total_count": 2
  }
}
```

## Create a Comment

```bash
curl -X POST https://api.taskmoor.com/v2/comments \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_042",
    "body": "Deployment to staging is complete. Test results look good.\n\n**Test summary:**\n- Unit tests: 142 passed\n- Integration tests: 38 passed\n- E2E tests: 12 passed"
  }'
```

### Create Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `task_id` | string | Yes | Task to attach the comment to |
| `body` | string | Yes | Comment body in Markdown (max 10,000 characters) |
| `parent_comment_id` | string | No | ID of the parent comment for threaded replies |

### Response

```json
{
  "id": "cmt_003",
  "task_id": "task_042",
  "author": {
    "id": "usr_007",
    "name": "Jordan Lee",
    "email": "jlee@example.com"
  },
  "body": "Deployment to staging is complete. Test results look good.\n\n**Test summary:**\n- Unit tests: 142 passed\n- Integration tests: 38 passed\n- E2E tests: 12 passed",
  "body_html": "<p>Deployment to staging is complete. Test results look good.</p><p><strong>Test summary:</strong></p><ul><li>Unit tests: 142 passed</li><li>Integration tests: 38 passed</li><li>E2E tests: 12 passed</li></ul>",
  "mentions": [],
  "reactions": [],
  "parent_comment_id": null,
  "created_at": "2026-07-16T16:00:00Z",
  "updated_at": "2026-07-16T16:00:00Z"
}
```

## Retrieve a Comment

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/comments/cmt_001"
```

## Delete a Comment

```bash
curl -X DELETE https://api.taskmoor.com/v2/comments/cmt_001 \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content`. Only the comment author or a workspace administrator can delete a comment. Deleting a parent comment does not delete its replies; replies become top-level comments.

## Mentions

To mention a user in a comment, include their user ID in the format `@usr_XXX` within the comment body. Taskmoor automatically resolves the ID to the user's display name in the rendered HTML and sends a notification to the mentioned user.

```bash
curl -X POST https://api.taskmoor.com/v2/comments \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_042",
    "body": "@usr_012 Please review the latest changes before EOD."
  }'
```

The response `mentions` array lists the user IDs that were successfully resolved.

## Threaded Replies

Create a reply to an existing comment by specifying `parent_comment_id`:

```bash
curl -X POST https://api.taskmoor.com/v2/comments \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task_042",
    "body": "Agreed, the error handling is solid. Merging now.",
    "parent_comment_id": "cmt_002"
  }'
```

Threads are limited to two levels of nesting. Attempting to reply to a reply returns a `422` validation error.

## Error Responses

| HTTP Status | Description |
|:-----------:|-------------|
| 400 | Malformed request body or empty comment body |
| 401 | Invalid or revoked API token (`API_ERR_401`) |
| 403 | Token lacks `comments:write` scope |
| 404 | Task or comment not found |
| 422 | Validation error (e.g., body exceeds 10,000 characters, nesting limit exceeded) |
