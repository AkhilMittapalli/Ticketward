---
doc_key: inc_2026_05_payment_processing
doc_type: known_incident
title: "Payment Processing Delays"
product_areas:
  - billing_subscriptions
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-05-25"
effective_from: "2026-05-18"
effective_to: "2026-05-18"
incident_status: resolved
started_at: "2026-05-18T09:30:00Z"
resolved_at: "2026-05-18T16:00:00Z"
affected_regions:
  - us
  - eu
error_codes:
  - PAY_ERR_DECLINED
  - PAY_ERR_3DS
last_update_at: "2026-05-18T16:00:00Z"
---

# Payment Processing Delays

## Summary

Payment processing for subscription renewals and plan upgrades experienced failures in the US and EU regions. Users encountered `PAY_ERR_DECLINED` errors on valid payment methods and `PAY_ERR_3DS` errors during 3D Secure authentication flows. New subscriptions, upgrades, and seat additions were affected.

## Timeline

**2026-05-18 09:30 UTC — Investigating**
Automated alerts detected a spike in payment failure rates. The billing team began investigating declined transactions.

**2026-05-18 11:00 UTC — Identified**
The payment gateway provider confirmed a partial outage on their side affecting 3D Secure authentication and certain card network validations. Taskmoor's payment integration was correctly submitting transactions, but the upstream provider was returning erroneous decline responses.

**2026-05-18 13:00 UTC — Mitigation Applied**
Taskmoor implemented a retry queue for failed payment transactions, holding them for automatic retry once the upstream provider confirmed resolution. Affected customers were not charged duplicate amounts.

**2026-05-18 16:00 UTC — Resolved**
The payment gateway provider resolved their issue. All queued payment retries completed successfully. Subscription statuses were updated and no accounts were incorrectly downgraded due to the payment failures.

## Root Cause

An upstream payment gateway provider experienced a partial outage affecting 3D Secure authentication and card network validation. Taskmoor's systems correctly detected and queued the failed transactions for retry.

## Resolution

Upstream provider restored service. Taskmoor's retry queue processed all held transactions without duplicates or missed payments. A payment provider health-check integration was added to proactively detect future upstream issues and display appropriate user-facing messaging.
