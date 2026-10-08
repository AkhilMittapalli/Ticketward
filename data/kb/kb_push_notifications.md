---
doc_key: kb_push_notifications
doc_type: help_article
title: "Configuring Push Notifications"
product_areas:
  - mobile_apps
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

Push notifications keep you informed about important activity in your Taskmoor workspace directly on your mobile device or desktop. Push notifications are available on all plans across iOS, Android, and the Taskmoor desktop app (version 3.2.0 or later).

## Setting Up Push Notifications

### Mobile (iOS and Android)

1. Install the Taskmoor app from the App Store (iOS 5.8.2+) or Google Play (Android 5.8.1+).
2. Sign in to your Taskmoor account.
3. When prompted, allow Taskmoor to send push notifications in your device's permission dialog.
4. If you dismissed the prompt, enable notifications manually:
   - **iOS**: Go to device **Settings > Notifications > Taskmoor** and enable **Allow Notifications**.
   - **Android**: Go to device **Settings > Apps > Taskmoor > Notifications** and enable the notification channel.

### Desktop App

1. Open the Taskmoor desktop app (version 3.2.0+).
2. Click your avatar in the bottom-left corner and select **Settings**.
3. Navigate to **Notifications > Desktop**.
4. Toggle **Push Notifications** on.
5. If your operating system prompts for notification permissions, allow them.

## Choosing Which Events Trigger Notifications

You can fine-tune which workspace events generate push notifications:

1. In the Taskmoor mobile or desktop app, go to **Settings > Notifications > Push**.
2. Toggle individual event types on or off:

| Event Category | Description | Default |
|---|---|---|
| **Assigned to me** | A task is assigned to you | On |
| **Mentioned** | You are @-mentioned in a comment or description | On |
| **Due date reminder** | A task you own is due within 24 hours | On |
| **Task completed** | A task you are following is marked complete | Off |
| **Status change** | A task you are following changes status | Off |
| **New comment** | A comment is added to a task you follow | On |
| **Project invitation** | You are invited to a new project | On |
| **Automation triggered** | An automation rule fires on a task you own (Starter+) | Off |

3. Click **Save**.

These preferences are per-device. If you use Taskmoor on multiple devices, configure notifications on each one separately.

## Quiet Hours (Do Not Disturb)

To prevent notifications during off-hours:

1. Go to **Settings > Notifications > Push > Quiet Hours**.
2. Toggle **Enable Quiet Hours** on.
3. Set your **Start Time** and **End Time** (e.g., 20:00 to 08:00).
4. Select applicable days (e.g., weekdays only, every day, or weekends only).
5. Click **Save**.

During quiet hours, notifications are held and delivered as a batch when quiet hours end. Critical alerts (workspace-level security events on Enterprise plans) bypass quiet hours.

## Notification Grouping

By default, Taskmoor groups push notifications by project on iOS and Android. If you receive multiple updates for the same project in a short window, they are collapsed into a single summary notification. Tapping the summary opens the full list.

To change grouping behavior on iOS, go to device **Settings > Notifications > Taskmoor > Notification Grouping** and select **Automatic**, **By Project**, or **Off**.

On Android, notification channels control grouping. Taskmoor creates separate channels for high-priority events (assignments, mentions) and low-priority events (status changes, comments). You can configure each channel independently in your device notification settings.

## Troubleshooting

### Not Receiving Push Notifications

- **Check device permissions.** Ensure Taskmoor has notification permission in your device settings.
- **Check in-app settings.** Verify the relevant event types are toggled on under **Settings > Notifications > Push**.
- **Check Quiet Hours.** If quiet hours are enabled, notifications may be held until the window ends.
- **Check battery optimization.** On Android, aggressive battery optimization can prevent push notifications. Go to device **Settings > Battery > Taskmoor** and select **Unrestricted** or **Not Optimized**.
- **Force close and reopen the app.** This re-registers the push notification token with Taskmoor's servers.
- **Check your internet connection.** Push notifications require an active connection to be received (queued notifications are delivered when the device reconnects).

### Duplicate Notifications

If you receive the same notification on both mobile and desktop, this is expected behavior when push notifications are enabled on multiple devices. To avoid duplicates, disable push notifications on one device or configure different event types per device.

### NOTIF_ERR_BOUNCE

On rare occasions, the push notification service reports a delivery failure. This is logged as NOTIF_ERR_BOUNCE in your notification activity log. The system automatically retries delivery up to three times. If the error persists, try signing out and back in to refresh your push token.

## Related Articles

- Daily Digest Settings
- Mobile Offline Mode
