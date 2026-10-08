---
doc_key: inc_2026_07_mobile_sync
doc_type: known_incident
title: "Mobile App Sync Failures"
product_areas:
  - mobile_apps
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-07-27"
effective_from: "2026-07-20"
effective_to: "2026-07-20"
incident_status: resolved
started_at: "2026-07-20T07:15:00Z"
resolved_at: "2026-07-20T14:45:00Z"
affected_regions:
  - us
  - eu
  - apac
error_codes:
  - MOB_ERR_SYNC
last_update_at: "2026-07-20T14:45:00Z"
---

# Mobile App Sync Failures

## Summary

Users of the Taskmoor iOS and Android mobile apps experienced sync failures across all regions. The apps displayed `MOB_ERR_SYNC` errors when attempting to pull updates or push local changes. Offline edits were preserved locally but could not be synchronized with the server.

## Timeline

**2026-07-20 07:15 UTC — Investigating**
User reports and automated monitoring flagged a global increase in mobile sync failures. Both iOS and Android apps were affected. The mobile backend team began investigation.

**2026-07-20 09:00 UTC — Identified**
The root cause was traced to a breaking schema change in the mobile sync API. A deployment at 06:50 UTC introduced a new required field in the sync payload that the current production versions of the mobile apps did not include. The server-side validation rejected sync requests missing this field.

**2026-07-20 10:30 UTC — Mitigation Applied**
A server-side hotfix was deployed to make the new field optional with a default value, restoring backward compatibility with existing mobile app versions.

**2026-07-20 14:45 UTC — Resolved**
Sync functionality fully restored across all regions. Locally queued changes synced successfully once the fix was deployed. No data loss occurred.

## Root Cause

A required field was added to the mobile sync API without maintaining backward compatibility with the deployed mobile app versions. The server-side validation was overly strict, rejecting payloads from apps that had not yet been updated with the new field.

## Resolution

The server-side API was updated to accept the field as optional. A backward-compatibility testing gate was added to the mobile API deployment checklist to prevent similar regressions.
