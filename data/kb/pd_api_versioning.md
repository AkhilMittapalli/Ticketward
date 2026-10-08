---
doc_key: pd_api_versioning
doc_type: product_doc
title: "API Versioning Policy and Deprecation"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-30"
effective_from: "2026-07-03"
effective_to: null
---

## Overview

Taskmoor follows a structured API versioning policy to ensure stability for existing integrations while enabling continued platform evolution. The current API version is v2, accessible at the base path `/v2`. This document describes the versioning scheme, backward compatibility guarantees, deprecation timeline, and migration guidance.

## Versioning Scheme

Taskmoor uses URL-based major versioning. The version number is part of the base URL path:

```
https://api.taskmoor.com/v2/tasks
```

Major version increments (e.g., v2 to v3) indicate breaking changes. Within a major version, Taskmoor makes only backward-compatible changes.

## Backward-Compatible Changes

The following changes are considered backward-compatible and may be introduced to the current version without notice:

- Adding new endpoints
- Adding new optional query parameters to existing endpoints
- Adding new fields to response objects
- Adding new enum values to response fields
- Adding new webhook event types
- Adding new error codes
- Increasing rate limits

Your integration should be designed to tolerate these changes. Specifically:

- Ignore unknown JSON fields in response bodies
- Do not rely on a fixed set of enum values for response fields
- Do not hard-code the exact set of returned fields

## Breaking Changes

The following changes are considered breaking and trigger a new major version:

- Removing an endpoint
- Removing or renaming a response field
- Changing the type of a response field
- Changing the behavior of an existing endpoint
- Removing support for a query parameter
- Changing authentication mechanisms
- Changing the error response format

## API Version Headers

Every API response includes headers indicating the version used and any applicable deprecation notices:

```
X-API-Version: v2
X-API-Deprecated: false
```

When an endpoint or feature is scheduled for removal, the headers include deprecation information:

```
X-API-Version: v2
X-API-Deprecated: true
X-API-Sunset-Date: 2027-06-01
X-API-Migration-Guide: https://docs.taskmoor.com/api/migration/v2-to-v3
```

## Deprecation Timeline

When Taskmoor deprecates an API feature or endpoint within a major version, the following timeline applies:

| Phase | Duration | Description |
|-------|:--------:|-------------|
| Announcement | Day 0 | Deprecation notice posted in changelog and API response headers |
| Warning | 90 days | Deprecated feature continues to work; `X-API-Deprecated: true` header included |
| Sunset | +90 days | Feature returns `410 Gone` with migration guidance |

For major version retirements (e.g., retiring v1 after v2 launch), the timeline extends:

| Phase | Duration | Description |
|-------|:--------:|-------------|
| Announcement | Day 0 | New major version released; migration guide published |
| Parallel support | 12 months | Both versions fully operational |
| Sunset warning | +6 months | Old version returns deprecation headers |
| Retirement | +6 months | Old version returns `410 Gone` |

Total timeline from new version launch to old version retirement: 24 months.

## Version Discovery

Query the API root to discover available versions:

```bash
curl https://api.taskmoor.com/
```

Response:

```json
{
  "versions": [
    {
      "version": "v2",
      "status": "current",
      "base_url": "https://api.taskmoor.com/v2",
      "released_at": "2025-09-01"
    },
    {
      "version": "v1",
      "status": "deprecated",
      "base_url": "https://api.taskmoor.com/v1",
      "sunset_date": "2027-03-01",
      "released_at": "2023-06-15"
    }
  ]
}
```

## Feature Flags and Preview Endpoints

New endpoints may be released as preview features under the current version. Preview endpoints are marked with a header:

```
X-API-Preview: true
```

Preview endpoints may change without notice and are not covered by the backward-compatibility guarantee. To opt in to preview endpoints, include the `X-Taskmoor-Preview` header:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  -H "X-Taskmoor-Preview: 2026-07" \
  https://api.taskmoor.com/v2/analytics/trends
```

Preview features that reach stability are promoted to general availability with a changelog announcement.

## Migration Notifications

Taskmoor notifies workspace administrators of upcoming deprecations through:

- In-app banner in the Taskmoor admin panel
- Email notifications at 90 days, 30 days, and 7 days before sunset
- API response headers on affected endpoints
- Entries in the platform changelog at `https://docs.taskmoor.com/changelog`

## Checking Your API Usage

Identify which deprecated endpoints your integration uses by reviewing API usage logs in **Settings > API > Usage > Deprecated Endpoints**. This report lists all deprecated endpoints called by each API token, helping you prioritize migration efforts.
