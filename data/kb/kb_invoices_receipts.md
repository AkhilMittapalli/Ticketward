---
doc_key: kb_invoices_receipts
doc_type: help_article
title: "Viewing Invoices and Receipts"
product_areas:
  - billing_subscriptions
plans_applicable:
  - free
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

## Overview

Taskmoor provides detailed invoices for every billing cycle and transaction. This article explains how to view, download, and manage your workspace invoices and receipts. Invoices are available on all plans, though Free plan workspaces only generate invoices if they have previously been on a paid plan.

## Prerequisites

- You must be a **Workspace Owner** to access billing and invoices.
- Admins, Members, and Limited Members cannot view invoices.

## Viewing Invoices

1. Log in to Taskmoor as a Workspace Owner.
2. Navigate to **Settings > Billing > Invoices**.
3. The invoice list displays all past invoices in reverse chronological order, including:
   - Invoice number
   - Billing period (start and end date)
   - Amount
   - Status (Paid, Pending, Failed, Refunded)
   - Payment method used (last four digits)

## Downloading an Invoice

1. Go to **Settings > Billing > Invoices**.
2. Find the invoice you want to download.
3. Click the **Download** icon next to the invoice.
4. Choose the format: **PDF** (default) or **CSV**.
5. The file is downloaded to your device.

PDF invoices include:
- Your workspace name and billing address.
- Taskmoor's company details and tax identification number.
- Line items for subscription charges, seat adjustments, and any prorated amounts.
- Tax amounts (where applicable).
- Total amount charged.

## Understanding Invoice Line Items

A typical monthly invoice contains the following:

| Line Item | Description |
|---|---|
| Subscription - [Plan Name] | Base subscription charge for the billing period |
| Seats (N x $X/seat) | Per-seat charge for the number of provisioned seats |
| Prorated adjustment | Credit or charge for mid-cycle seat changes |
| Tax | Applicable sales tax, VAT, or GST |
| **Total** | **Sum of all line items** |

### Prorated Charges

If you add or remove seats during a billing cycle, the invoice includes a prorated adjustment:

- **Adding seats**: You are charged for the remaining days in the current billing period at the per-seat rate.
- **Removing seats**: A credit is applied for the remaining days of the unused seats. The credit appears on the next invoice.

### Annual Billing

If your workspace is on annual billing, the invoice shows the full annual amount at the start of each billing year. Mid-year seat additions are charged at the prorated annual rate.

## Receipts

Receipts are generated automatically after each successful payment. To access receipts:

1. Go to **Settings > Billing > Invoices**.
2. Click on the invoice with status **Paid**.
3. Click **View Receipt**.

Receipts confirm the payment amount, date, and method. They are suitable for expense reporting and reimbursement.

## Adding Billing Information

To include your company name, address, or tax ID on invoices:

1. Go to **Settings > Billing > Billing Information**.
2. Enter or update:
   - Company name
   - Billing address
   - Tax identification number (VAT ID, GST number, etc.)
3. Click **Save**.

Updated billing information appears on all future invoices. Previously generated invoices are not retroactively updated. If you need a corrected invoice for a past period, contact Taskmoor support.

## Email Invoice Delivery

Invoices are emailed to the Workspace Owner's email address after each billing cycle. To add additional recipients:

1. Go to **Settings > Billing > Billing Information**.
2. Under **Invoice Recipients**, click **Add Email**.
3. Enter the email address (e.g., your finance team).
4. Click **Save**.

You can add up to 5 additional invoice recipient email addresses.

## Failed Payments

If a payment fails, the invoice status shows **Failed**. Taskmoor retries the payment up to 3 times over 10 days. During this period:

- The invoice remains in Failed status.
- The workspace continues to operate normally.
- Workspace Owners receive email notifications about the failed payment.

If all retries fail, the workspace enters a 14-day grace period. Update your payment method to resolve the issue. See the payment methods article for details on handling errors PAY_ERR_DECLINED, PAY_ERR_3DS, and PAY_ERR_EXPIRED.

## Enterprise Invoicing

Enterprise customers on contract-based billing receive invoices according to their contract terms (monthly, quarterly, or annually). Enterprise invoices are managed by Taskmoor's finance team and may differ in format from self-service invoices. Contact your account representative for invoice inquiries.

## Troubleshooting

### Invoice is missing or not received via email

- Check the spam or junk folder of the Workspace Owner's email.
- Verify the email address in **Account Settings** is correct.
- If the error NOTIF_ERR_BOUNCE has been flagged for the email address, Taskmoor may have stopped sending emails to it. Contact support to clear the flag.

### Invoice shows an unexpected amount

- Review the line items for prorated seat adjustments. Adding or removing seats mid-cycle changes the invoice total.
- If you switched plans during the billing cycle, both the old and new plan charges may appear on the same invoice.
- Contact Taskmoor support if the amount still seems incorrect.
