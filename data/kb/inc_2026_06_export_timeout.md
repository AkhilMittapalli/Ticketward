---
doc_key: inc_2026_06_export_timeout
doc_type: known_incident
title: "Data Export Timeouts for Large Projects"
product_areas:
  - data_import_export
  - reporting_analytics
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-06-13"
effective_from: "2026-06-05"
effective_to: "2026-06-06"
incident_status: resolved
started_at: "2026-06-05T13:00:00Z"
resolved_at: "2026-06-06T02:30:00Z"
affected_regions:
  - us
error_codes:
  - EXP_ERR_SIZE
  - RPT_ERR_TIMEOUT
last_update_at: "2026-06-06T02:30:00Z"
---

# Data Export Timeouts for Large Projects

## Summary

Users in the US region experienced timeouts when attempting to export project data or generate reports for projects exceeding approximately 1,000 tasks. Exports returned `EXP_ERR_SIZE` errors, and report generation requests timed out with `RPT_ERR_TIMEOUT`. Smaller exports and reports functioned normally.

## Timeline

**2026-06-05 13:00 UTC — Investigating**
Customer reports indicated that CSV and PDF exports were failing for large projects. The data services team confirmed the issue and began investigation.

**2026-06-05 15:30 UTC — Identified**
Root cause identified as a memory allocation issue in the export worker pool. A recent infrastructure update changed the memory limits on export worker containers from 4GB to 2GB. Large project exports exceeded the new memory ceiling, causing out-of-memory terminations that surfaced as timeout errors to the user.

**2026-06-05 18:00 UTC — Mitigation Applied**
Memory limits on export worker containers were restored to 4GB. Additionally, the export pipeline was updated to implement chunked processing for projects with more than 2,000 tasks, reducing peak memory consumption.

**2026-06-06 02:30 UTC — Resolved**
All queued exports completed successfully. The export system was confirmed stable under load testing with projects up to 10,000 tasks.

## Root Cause

An infrastructure configuration change reduced the memory allocation for export worker containers, causing out-of-memory failures on large project exports. The export pipeline lacked chunked processing, making it sensitive to memory constraints.

## Resolution

Memory limits were restored and chunked export processing was implemented. Infrastructure configuration changes affecting worker resource limits now require sign-off from the data services team lead.
