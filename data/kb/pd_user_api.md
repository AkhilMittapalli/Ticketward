---
doc_key: pd_user_api
doc_type: product_doc
title: "Users API Endpoint Reference"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-14"
effective_from: "2026-07-18"
effective_to: null
---

## Overview

The Users API provides read-only access to workspace member profiles and read-write access to user invitations. User profiles are managed through workspace settings or SCIM provisioning (Enterprise). This endpoint is available on Starter, Business, and Enterprise plans.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v2/users` | List workspace members |
| `GET` | `/v2/users/{user_id}` | Retrieve a single user profile |
| `POST` | `/v2/users/invite` | Invite a new member to the workspace |
| `DELETE` | `/v2/users/{user_id}` | Remove a member from the workspace |

## List Users

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/users?role=member&status=active&limit=50"
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `status` | string | null | Filter by status: `active`, `deactivated`, `pending` |
| `role` | string | null | Filter by workspace role: `owner`, `admin`, `member`, `guest` |
| `search` | string | null | Search by name or email |
| `sort` | string | `name` | Sort field: `name`, `email`, `created_at`, `last_active_at` |
| `order` | string | `asc` | Sort order: `asc` or `desc` |
| `limit` | integer | 50 | Results per page (max: 100) |
| `cursor` | string | null | Pagination cursor |

### Response

```json
{
  "data": [
    {
      "id": "usr_001",
      "email": "admin@example.com",
      "name": "Alex Johnson",
      "first_name": "Alex",
      "last_name": "Johnson",
      "avatar_url": "https://cdn.taskmoor.com/avatars/usr_001.png",
      "role": "owner",
      "status": "active",
      "job_title": "CTO",
      "department": "Engineering",
      "timezone": "America/New_York",
      "last_active_at": "2026-07-18T15:30:00Z",
      "created_at": "2025-01-15T08:00:00Z"
    },
    {
      "id": "usr_007",
      "email": "jlee@example.com",
      "name": "Jordan Lee",
      "first_name": "Jordan",
      "last_name": "Lee",
      "avatar_url": "https://cdn.taskmoor.com/avatars/usr_007.png",
      "role": "member",
      "status": "active",
      "job_title": "Senior Engineer",
      "department": "Engineering",
      "timezone": "America/Los_Angeles",
      "last_active_at": "2026-07-18T14:00:00Z",
      "created_at": "2025-03-10T10:00:00Z"
    }
  ],
  "pagination": {
    "cursor": "eyJ1c2VyIjoianVzXzAwNyJ9",
    "has_more": true,
    "total_count": 45
  }
}
```

## Retrieve a User

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/users/usr_007"
```

Returns the full user profile object. The response includes all fields shown in the list response, plus:

```json
{
  "id": "usr_007",
  "email": "jlee@example.com",
  "name": "Jordan Lee",
  "first_name": "Jordan",
  "last_name": "Lee",
  "role": "member",
  "status": "active",
  "job_title": "Senior Engineer",
  "department": "Engineering",
  "timezone": "America/Los_Angeles",
  "locale": "en-US",
  "projects": [
    {"id": "proj_001", "name": "Platform Redesign", "role": "member"},
    {"id": "proj_005", "name": "API Gateway", "role": "admin"}
  ],
  "two_factor_enabled": true,
  "sso_provider": null,
  "last_active_at": "2026-07-18T14:00:00Z",
  "created_at": "2025-03-10T10:00:00Z"
}
```

## Invite a User

Send an invitation to add a new member to the workspace:

```bash
curl -X POST https://api.taskmoor.com/v2/users/invite \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newmember@example.com",
    "role": "member",
    "project_ids": ["proj_001", "proj_005"],
    "message": "Welcome to the team! You have been added to the Platform Redesign and API Gateway projects."
  }'
```

### Invite Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `email` | string | Yes | Email address of the invitee |
| `role` | string | No | Workspace role: `member` (default), `admin`, or `guest` |
| `project_ids` | array | No | Projects to add the user to upon acceptance |
| `message` | string | No | Custom invitation message (max 500 characters) |

### Response

```json
{
  "id": "usr_050",
  "email": "newmember@example.com",
  "status": "pending",
  "role": "member",
  "invitation_sent_at": "2026-07-18T10:00:00Z",
  "invitation_expires_at": "2026-07-25T10:00:00Z"
}
```

Invitations expire after 7 days. The API returns `409 Conflict` if the email is already associated with an active workspace member.

## Remove a User

```bash
curl -X DELETE https://api.taskmoor.com/v2/users/usr_050 \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content`. Removing a user deactivates their account and unassigns them from all tasks. Their historical data (comments, activity log) is preserved. Only workspace owners and admins can remove members.

Removing the last workspace owner is not permitted and returns `403 Forbidden`.

## Retrieve the Current User

Get the profile of the user associated with the API token:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/users/me"
```

This is useful for verifying token ownership and retrieving the authenticated user's workspace role.

## Error Responses

| HTTP Status | Description |
|:-----------:|-------------|
| 401 | Invalid or revoked API token (`API_ERR_401`) |
| 403 | Token lacks `users:read` or `users:write` scope |
| 404 | User not found in this workspace |
| 409 | Email already exists as an active workspace member |
| 422 | Validation error (e.g., invalid email format, invalid role) |

## SCIM Provisioning Note

Enterprise workspaces using SCIM provisioning should manage user creation and deactivation through the SCIM endpoint (`/scim/v2/Users`) rather than the REST API invite/remove endpoints. The SCIM integration synchronizes user lifecycle events with your identity provider automatically. See the SCIM Setup Guide for details.
