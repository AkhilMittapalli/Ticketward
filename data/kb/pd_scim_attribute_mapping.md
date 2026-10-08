---
doc_key: pd_scim_attribute_mapping
doc_type: product_doc
title: "SCIM Attribute Mapping Reference"
product_areas:
  - sso_identity
plans_applicable:
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-01"
effective_from: "2026-07-05"
effective_to: null
---

## Overview

Taskmoor's SCIM 2.0 implementation maps identity provider (IdP) attributes to Taskmoor user profile fields. This reference documents the supported SCIM attributes, required mappings, custom extensions, and common mapping issues. SCIM provisioning is available exclusively on the Enterprise plan.

## SCIM Endpoint

All SCIM operations target the base endpoint:

```
https://api.taskmoor.com/scim/v2/Users
```

## Core Attribute Mappings

The following SCIM core schema attributes (`urn:ietf:params:scim:schemas:core:2.0:User`) are supported:

| SCIM Attribute | Taskmoor Field | Required | Type | Description |
|----------------|---------------|:--------:|------|-------------|
| `userName` | `email` | Yes | string | Primary email; must be unique within the workspace |
| `name.givenName` | `first_name` | Yes | string | User's first name |
| `name.familyName` | `last_name` | Yes | string | User's last name |
| `displayName` | `display_name` | No | string | Full display name; defaults to `givenName + familyName` |
| `emails[primary].value` | `email` | Conditional | string | Primary email if `userName` is not an email format |
| `active` | `status` | No | boolean | `true` = active, `false` = deactivated |
| `title` | `job_title` | No | string | User's job title |
| `locale` | `locale` | No | string | IETF language tag (e.g., `en-US`) |
| `timezone` | `timezone` | No | string | IANA timezone (e.g., `America/New_York`) |
| `externalId` | `external_id` | No | string | IdP-assigned identifier for correlation |

## Taskmoor Enterprise Extension

Taskmoor defines a custom SCIM extension schema for additional attributes:

**Schema URI**: `urn:ietf:params:scim:schemas:extension:taskmoor:2.0:User`

| Extension Attribute | Taskmoor Field | Type | Description |
|--------------------|---------------|------|-------------|
| `department` | `department` | string | User's department within the organization |
| `role` | `workspace_role` | string | Workspace role: `member`, `admin`, or `guest` |
| `defaultProjectId` | `default_project_id` | string | Default project assignment on provisioning |

### Example: Create User with Extension Attributes

```bash
curl -X POST https://api.taskmoor.com/scim/v2/Users \
  -H "Authorization: Bearer tm_test_scim_token_789" \
  -H "Content-Type: application/scim+json" \
  -d '{
    "schemas": [
      "urn:ietf:params:scim:schemas:core:2.0:User",
      "urn:ietf:params:scim:schemas:extension:taskmoor:2.0:User"
    ],
    "userName": "mchen@example.com",
    "name": {
      "givenName": "Maya",
      "familyName": "Chen"
    },
    "emails": [
      {"value": "mchen@example.com", "primary": true}
    ],
    "active": true,
    "title": "Engineering Manager",
    "timezone": "America/Los_Angeles",
    "urn:ietf:params:scim:schemas:extension:taskmoor:2.0:User": {
      "department": "Engineering",
      "role": "admin",
      "defaultProjectId": "proj_005"
    }
  }'
```

Response:

```json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:taskmoor:2.0:User"
  ],
  "id": "usr_042",
  "userName": "mchen@example.com",
  "name": {
    "givenName": "Maya",
    "familyName": "Chen"
  },
  "emails": [
    {"value": "mchen@example.com", "primary": true}
  ],
  "active": true,
  "title": "Engineering Manager",
  "timezone": "America/Los_Angeles",
  "urn:ietf:params:scim:schemas:extension:taskmoor:2.0:User": {
    "department": "Engineering",
    "role": "admin",
    "defaultProjectId": "proj_005"
  },
  "meta": {
    "resourceType": "User",
    "created": "2026-07-05T14:00:00Z",
    "lastModified": "2026-07-05T14:00:00Z",
    "location": "https://api.taskmoor.com/scim/v2/Users/usr_042"
  }
}
```

## IdP-Specific Mapping Guides

### Okta Attribute Mapping

| Okta Profile Attribute | SCIM Attribute |
|------------------------|----------------|
| `user.email` | `userName` |
| `user.firstName` | `name.givenName` |
| `user.lastName` | `name.familyName` |
| `user.displayName` | `displayName` |
| `user.title` | `title` |
| `user.department` | `urn:...:taskmoor:2.0:User.department` |

### Azure AD Attribute Mapping

| Azure AD Attribute | SCIM Attribute |
|--------------------|----------------|
| `userPrincipalName` | `userName` |
| `givenName` | `name.givenName` |
| `surname` | `name.familyName` |
| `displayName` | `displayName` |
| `jobTitle` | `title` |
| `department` | `urn:...:taskmoor:2.0:User.department` |

## Error Handling

### SCIM_ERR_422: Invalid Attribute Mapping

This error occurs when the SCIM payload fails validation. Common causes:

| Issue | Example | Fix |
|-------|---------|-----|
| Missing `userName` | Payload has no `userName` field | Map the IdP email field to `userName` |
| Invalid email format | `userName: "not-an-email"` | Ensure `userName` contains a valid email |
| Unknown role value | `role: "superadmin"` | Use `member`, `admin`, or `guest` |
| Invalid timezone | `timezone: "PST"` | Use IANA format: `America/Los_Angeles` |

### SCIM_ERR_409: User Already Exists

Returned when a SCIM POST attempts to create a user whose `userName` already exists in the workspace. Use PATCH to update an existing user instead.

## Filtering Users

Query provisioned users using SCIM filter syntax:

```bash
curl -G https://api.taskmoor.com/scim/v2/Users \
  -H "Authorization: Bearer tm_test_scim_token_789" \
  --data-urlencode 'filter=userName eq "mchen@example.com"'
```

Supported filter operators: `eq`, `ne`, `co` (contains), `sw` (starts with).

## Attribute Sync Frequency

When connected to an IdP, attribute synchronization occurs:

- **On login**: Attributes are refreshed each time the user authenticates via SAML SSO.
- **On IdP push**: When the IdP pushes an update via SCIM PATCH or PUT.
- **Scheduled sync**: Taskmoor polls the IdP every 60 minutes for attribute changes (configurable in Settings > Security > SCIM).
