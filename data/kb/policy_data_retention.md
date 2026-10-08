---
doc_key: policy_data_retention
doc_type: policy
title: "Data Retention and Deletion Policy"
product_areas:
  - user_admin_permissions
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: admin
review_due_at: "2026-10-13"
effective_from: "2026-07-15"
effective_to: null
---

# Data Retention and Deletion Policy

## 1. Purpose

This document describes Taskmoor's data retention periods, deletion procedures, and compliance obligations under applicable data protection regulations, including the General Data Protection Regulation (GDPR) Articles 15 and 17.

## 2. Data Retention Periods

### 2.1 Active Accounts

All customer data, including projects, tasks, boards, attachments, comments, and user profiles, is retained for the duration of the active subscription. Data is available in full to workspace administrators and authorized users for the lifetime of the account.

### 2.2 Cancelled Accounts

Upon cancellation, Taskmoor retains workspace data for 30 calendar days to allow re-activation or data export. After the 30-day retention window, all workspace data is scheduled for permanent deletion. Once deletion begins, it is irreversible.

### 2.3 Free Plan Inactive Workspaces

Free plan workspaces that have had no user login activity for 365 consecutive days are flagged as inactive. The workspace administrator is notified by email 30 days before deletion. If no action is taken, the workspace data is permanently deleted.

### 2.4 Audit and System Logs

Audit logs are retained for 90 days on Business plans and 1 year on Enterprise plans. System-level operational logs (not containing customer content) are retained for up to 2 years for troubleshooting and compliance purposes.

## 3. Data Export

Workspace administrators may export their data at any time from the Taskmoor workspace settings panel. Exports include projects, tasks, comments, attachments, and user information in standard formats (JSON, CSV). Enterprise customers may request a full data archive through their Customer Success Manager.

Customers planning to cancel their subscription should complete any data export before the cancellation effective date to ensure full access during the export process.

## 4. Right of Access (GDPR Article 15)

Data subjects may submit a request to access the personal data that Taskmoor processes about them. Requests should be directed to privacy@taskmoor.com. Taskmoor will verify the identity of the requester and respond within 30 calendar days. Where requests are complex or numerous, the response period may be extended by an additional 60 days with prior notice.

## 5. Right to Erasure (GDPR Article 17)

Data subjects may request the deletion of their personal data by contacting privacy@taskmoor.com. Upon verification, Taskmoor will erase the personal data within 30 calendar days unless retention is required by legal obligation, defense of legal claims, or other exemptions under GDPR Article 17(3).

Erasure applies to the individual's personal data (profile information, activity records, comments attributed to them). Workspace-level project data and task records may be anonymized rather than deleted where the data is required for the workspace's continued operation.

## 6. Deletion Process

Data deletion is carried out in two phases:

1. **Soft Delete:** Data is removed from production systems and is no longer accessible to users. This occurs within 7 business days of the deletion trigger.
2. **Hard Delete:** Data is purged from all backup and archival systems within 90 calendar days of the soft delete.

## 7. Sub-Processor Data

When customer data has been shared with authorized sub-processors, Taskmoor will instruct those sub-processors to delete the relevant data in accordance with the data processing agreements in place.

## 8. Contact

For data access, erasure, or retention inquiries, contact privacy@taskmoor.com.
