---
doc_key: inc_2026_03_board_rendering
doc_type: known_incident
title: "Board View Rendering Failures"
product_areas:
  - boards_timelines
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-03-29"
effective_from: "2026-03-22"
effective_to: "2026-03-22"
incident_status: resolved
started_at: "2026-03-22T11:30:00Z"
resolved_at: "2026-03-22T19:00:00Z"
affected_regions:
  - apac
error_codes:
  - BOARD_ERR_RENDER
last_update_at: "2026-03-22T19:00:00Z"
---

# Board View Rendering Failures

## Summary

Users in the APAC region encountered `BOARD_ERR_RENDER` errors when loading Kanban board views and timeline views. The board interface either failed to render entirely or displayed incomplete card layouts. List views and other project views were unaffected.

## Timeline

**2026-03-22 11:30 UTC — Investigating**
Multiple APAC users reported board views failing to load. The frontend platform team confirmed the issue was isolated to the APAC CDN edge nodes serving the board rendering assets.

**2026-03-22 13:00 UTC — Identified**
A corrupted JavaScript bundle for the board rendering module was cached on the APAC CDN edge nodes. The corruption occurred during a deployment at 10:45 UTC when a partial upload was cached before the full bundle transfer completed.

**2026-03-22 15:00 UTC — Mitigation Applied**
The corrupted cache was purged from all APAC edge nodes and the correct bundle was re-deployed. Users were advised to perform a hard refresh to pick up the corrected assets.

**2026-03-22 19:00 UTC — Resolved**
Board rendering was fully restored across the APAC region. The CDN cache was verified clean and serving the correct bundle version.

## Root Cause

A partial JavaScript bundle upload was cached by APAC CDN edge nodes before the full asset transfer completed, resulting in a corrupted rendering module being served to users.

## Resolution

CDN cache was purged and the correct assets were deployed. The deployment pipeline was updated to perform an atomic asset swap with cache invalidation, preventing partial uploads from being served. A post-deploy content-integrity check was added to verify bundle checksums against the expected manifest.
