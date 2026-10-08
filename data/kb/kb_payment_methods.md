---
doc_key: kb_payment_methods
doc_type: help_article
title: "Updating Payment Methods"
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
review_due_at: "2026-12-12"
effective_from: "2026-06-15"
effective_to: null
---

## Overview

This article covers how to add, update, and manage payment methods for your Taskmoor workspace. A valid payment method is required to maintain a paid subscription (Starter, Business, or Enterprise). Free plan workspaces do not require a payment method but can add one in preparation for an upgrade.

## Prerequisites

- You must be a **Workspace Owner** to manage payment methods.
- Admins, Members, and Limited Members do not have access to billing settings.

## Supported Payment Methods

Taskmoor accepts the following payment methods:

- **Credit cards**: Visa, Mastercard, American Express.
- **Debit cards**: Visa Debit, Mastercard Debit.
- **Wire transfer / Invoice**: Available for Enterprise plans only, by arrangement with Taskmoor sales.

Prepaid cards and virtual cards are accepted but may not work for recurring subscriptions if the card has a balance limit or expiration.

## Adding a Payment Method

1. Log in to Taskmoor as a Workspace Owner.
2. Navigate to **Settings > Billing > Payment Methods**.
3. Click **Add Payment Method**.
4. Enter the card details:
   - Cardholder name
   - Card number
   - Expiration date
   - CVV/CVC
5. Enter the billing address.
6. Click **Save Card**.

Your payment processor may require 3D Secure (3DS) verification. If prompted, complete the verification step in the pop-up window provided by your bank.

## Updating an Existing Payment Method

To replace your current card with a new one:

1. Go to **Settings > Billing > Payment Methods**.
2. Click **Add Payment Method** to add the new card.
3. After the new card is saved, it is automatically set as the default payment method.
4. Optionally, remove the old card by clicking the options menu next to it and selecting **Remove**.

You cannot edit an existing card's details directly. Instead, add a new card and remove the old one.

## Setting the Default Payment Method

If you have multiple payment methods on file:

1. Go to **Settings > Billing > Payment Methods**.
2. Find the card you want to use for future charges.
3. Click the options menu and select **Set as Default**.

All future subscription charges and seat additions are billed to the default payment method.

## Troubleshooting Payment Errors

### PAY_ERR_DECLINED

The card was declined by the issuing bank. Common reasons include:

- Insufficient funds.
- The card has been reported lost or stolen.
- The bank flagged the transaction as suspicious.

**Resolution**: Try a different card or contact your bank to authorize the charge. Then retry from **Settings > Billing > Payment Methods**.

### PAY_ERR_3DS

3D Secure verification failed. This happens when:

- The verification pop-up was closed before completion.
- The bank's authentication service timed out.
- The card does not support 3D Secure.

**Resolution**: Retry the payment and complete the 3DS verification step. If your card does not support 3DS, try a different card. Ensure your browser allows pop-ups from Taskmoor.

### PAY_ERR_EXPIRED

The card on file has expired.

**Resolution**: Add a new card with a valid expiration date and remove the expired card.

### Subscription suspended due to payment failure

If a payment attempt fails, Taskmoor retries up to 3 times over 10 days. After the final retry fails:

- The workspace is moved to a **grace period** of 14 days.
- During the grace period, all features remain accessible, but a banner warns Workspace Owners to update payment information.
- After the grace period, the workspace is downgraded to the Free plan. Features above the Free tier become read-only.

To restore your paid subscription:

1. Add a valid payment method.
2. Go to **Settings > Billing > Subscription**.
3. Click **Reactivate Subscription**.
4. Select your desired plan and confirm.
5. Any outstanding balance is charged to the new payment method.

## Enterprise Billing

Enterprise customers on invoice-based billing do not manage payment methods in the Taskmoor UI. Invoices are sent according to the terms agreed with Taskmoor sales. Contact your account representative for billing inquiries.

## Security

- Payment card details are processed by a PCI DSS Level 1 certified payment processor. Taskmoor does not store full card numbers.
- All payment pages use TLS encryption.
- Workspace Owners can view the last four digits of saved cards but cannot see full card details.
