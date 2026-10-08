---
doc_key: pd_api_pagination
doc_type: product_doc
title: "API Pagination: Cursor-Based Pagination Patterns"
product_areas:
  - integrations_api
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-25"
effective_from: "2026-06-28"
effective_to: null
---

## Overview

Taskmoor REST API v2 uses cursor-based pagination for all collection endpoints. Cursor-based pagination provides stable results even when the underlying data changes between requests, making it suitable for incremental data synchronization and large dataset traversal.

## How Cursor Pagination Works

When you request a collection endpoint, the response includes a `pagination` object with a `cursor` value. To retrieve the next page, pass this cursor as a query parameter in the subsequent request.

### Initial Request

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks?limit=10"
```

Response:

```json
{
  "data": [
    {"id": "task_100", "title": "Design system audit"},
    {"id": "task_099", "title": "API documentation review"}
  ],
  "pagination": {
    "cursor": "eyJpZCI6InRhc2tfMDk5IiwidHMiOiIyMDI2LTA2LTI4VDEwOjAwOjAwWiJ9",
    "has_more": true,
    "total_count": 342
  }
}
```

### Next Page Request

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks?limit=10&cursor=eyJpZCI6InRhc2tfMDk5IiwidHMiOiIyMDI2LTA2LTI4VDEwOjAwOjAwWiJ9"
```

### Final Page

When `has_more` is `false`, you have reached the end of the collection:

```json
{
  "data": [
    {"id": "task_002", "title": "Initialize project"},
    {"id": "task_001", "title": "Workspace setup"}
  ],
  "pagination": {
    "cursor": null,
    "has_more": false,
    "total_count": 342
  }
}
```

## Pagination Parameters

| Parameter | Type | Default | Description |
|-----------|------|:-------:|-------------|
| `limit` | integer | 50 | Number of results per page. Minimum: 1, Maximum: 100 |
| `cursor` | string | null | Opaque cursor from a previous response's `pagination.cursor` |

## Pagination Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `cursor` | string or null | Cursor to pass for the next page; `null` on the last page |
| `has_more` | boolean | `true` if more results exist beyond this page |
| `total_count` | integer | Total number of resources matching the query (approximate for large datasets) |

## Combining Pagination with Filters

Cursor pagination works alongside all query filters. Filters are applied before pagination, and the cursor maintains the filter context:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks?status=in_progress&assignee_id=usr_007&limit=25"
```

When paginating, include the same filter parameters along with the cursor. The cursor encodes the sort position, but filters must be repeated:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks?status=in_progress&assignee_id=usr_007&limit=25&cursor=eyJpZCI6InRhc2tfMDc1In0="
```

## Sorting and Pagination

Cursor pagination respects the `sort` and `order` parameters. The default sort is `created_at` descending.

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks?sort=updated_at&order=asc&limit=20"
```

Once you begin paginating with a cursor, do not change the `sort` or `order` parameters between pages. Changing them invalidates the cursor and may produce inconsistent results.

## Full Collection Traversal Example

This example iterates through all tasks in a workspace:

```bash
#!/bin/bash
CURSOR=""
PAGE=1

while true; do
  if [ -z "$CURSOR" ]; then
    RESPONSE=$(curl -s -H "Authorization: Bearer tm_test_abc123def456" \
      "https://api.taskmoor.com/v2/tasks?limit=100")
  else
    RESPONSE=$(curl -s -H "Authorization: Bearer tm_test_abc123def456" \
      "https://api.taskmoor.com/v2/tasks?limit=100&cursor=$CURSOR")
  fi

  echo "Page $PAGE: $(echo "$RESPONSE" | jq '.data | length') tasks"

  HAS_MORE=$(echo "$RESPONSE" | jq -r '.pagination.has_more')
  if [ "$HAS_MORE" = "false" ]; then
    break
  fi

  CURSOR=$(echo "$RESPONSE" | jq -r '.pagination.cursor')
  PAGE=$((PAGE + 1))
done
```

## Incremental Sync Pattern

Use the `updated_after` filter with pagination to synchronize only records that changed since your last sync:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/tasks?updated_after=2026-06-27T00:00:00Z&sort=updated_at&order=asc&limit=100"
```

Store the `updated_at` timestamp of the last record processed and use it as the `updated_after` value in the next sync run.

## Cursor Expiration

Cursors are valid for 24 hours from the time of the response that generated them. After expiration, the API returns a `400 Bad Request` with a message indicating the cursor is no longer valid. Restart pagination from the beginning with a fresh request.

## Best Practices

- Use the maximum `limit` of 100 to minimize the number of requests needed for full traversal.
- Do not decode or construct cursors manually; treat them as opaque strings.
- Always check `has_more` rather than assuming a fixed number of pages.
- For large-scale exports, consider using the `/v2/exports` endpoint instead of paginating through individual records.
