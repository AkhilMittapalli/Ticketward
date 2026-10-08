---
doc_key: kb_mobile_offline
doc_type: help_article
title: "Using Mobile Offline Mode"
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
review_due_at: "2026-12-12"
effective_from: "2026-06-15"
effective_to: null
---

## Overview

Taskmoor's mobile apps for iOS and Android include offline mode, allowing you to view and edit tasks even when you have no internet connection. Changes made offline are automatically synced when connectivity is restored. Offline mode is available on all plans.

## Supported App Versions

- **iOS**: Version 5.8.2 or later
- **Android**: Version 5.8.1 or later

Ensure your app is updated to the latest version from the App Store or Google Play to access all offline features.

## How Offline Mode Works

### Automatic Caching

When you open the Taskmoor mobile app while connected to the internet, the app downloads and caches data for the projects you have accessed recently (within the last 7 days). This cached data is stored locally on your device and becomes available when you go offline.

The app caches the following data per project:

- Task list with titles, descriptions, statuses, priorities, and assignees
- Comments (most recent 50 per task)
- Custom field values (Starter+ plans)
- Board views (Kanban layout and card positions)
- Subtask hierarchies

The app does **not** cache the following offline:

- File attachments (only metadata is cached; the file itself requires a connection to download)
- Timeline and Gantt views (these require server-side rendering)
- Dashboard widgets and reporting data
- Automation rule configurations

### Working Offline

When you lose connectivity, a banner appears at the top of the app indicating **Offline Mode**. You can continue to:

- View cached tasks and their details
- Create new tasks
- Edit task titles, descriptions, statuses, priorities, and assignees
- Add comments to tasks
- Mark tasks as complete
- Reorder tasks on the Kanban board

All changes are queued locally in a sync buffer.

### Syncing When Back Online

When connectivity is restored, the app automatically begins syncing queued changes. A sync indicator appears in the top navigation bar showing progress. The sync process works as follows:

1. **Queued changes are uploaded** in the order they were made.
2. **Conflict detection** runs if the same task was modified by another user while you were offline.
3. **Conflict resolution**: Taskmoor uses a last-write-wins strategy at the field level. If you edited a task's status offline and another user edited the same task's description, both changes are preserved. If both users changed the same field, the most recent change (by timestamp) takes precedence, and the overwritten change is logged in the task's activity history.

## Managing Offline Storage

Cached data consumes storage on your device. To manage offline storage:

1. Open the Taskmoor app and tap your **avatar** in the bottom navigation bar.
2. Go to **Settings > Offline & Storage**.
3. View the total storage used by Taskmoor's offline cache.
4. To clear the cache, tap **Clear Offline Data**. This removes all cached project data. The next time you connect to the internet, the app re-downloads data for your recent projects.

You can also select specific projects to exclude from offline caching:

1. In **Settings > Offline & Storage**, tap **Manage Projects**.
2. Toggle off any projects you do not need offline.

## Troubleshooting

### MOB_ERR_SYNC

This error appears when the sync process encounters an unrecoverable conflict or a server-side validation error. Common causes:

- A task you edited offline was deleted by another user before sync completed. The app discards the queued change and logs it in **Settings > Offline & Storage > Sync History**.
- You attempted to set a task dependency offline, but the dependency would create a cycle (TASK_ERR_DEP_CYCLE). The dependency change is rejected during sync.

To resolve persistent MOB_ERR_SYNC errors, try clearing your offline data and allowing the app to re-cache.

### MOB_ERR_SESSION

This error indicates your authentication session expired while you were offline. You will be prompted to sign in again when connectivity is restored. After signing in, any queued offline changes will resume syncing.

### Offline Data Not Available

If you open the app offline and see no data, the cache may have been cleared or the app may not have had a chance to cache data while connected. Ensure you open the app and navigate to your projects while connected at least once before going offline.

## Related Articles

- Push Notification Settings
- Kanban Boards
