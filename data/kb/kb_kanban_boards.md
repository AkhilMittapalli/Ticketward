---
doc_key: kb_kanban_boards
doc_type: help_article
title: "Using Kanban Boards"
product_areas:
  - boards_timelines
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

Kanban boards in Taskmoor provide a visual way to manage tasks by organizing them into columns that represent workflow stages. Drag tasks between columns as they progress through your process. Kanban boards are available on all plans.

## Accessing the Board View

1. Open a project from the Taskmoor sidebar.
2. Click the **Board** tab in the project header (next to List and other view options).
3. The board displays tasks as cards organized into status columns.

## Understanding Board Structure

### Columns

Each column corresponds to a status in your project workflow. The default project template includes:

- **To Do** -- Tasks not yet started.
- **In Progress** -- Tasks actively being worked on.
- **Review** -- Tasks awaiting review or approval.
- **Done** -- Completed tasks.

You can customize statuses (and therefore columns) in **Project Settings > Statuses**.

### Cards

Each card represents a task and displays:

- Task title
- Assignee avatar
- Priority indicator (colored flag)
- Due date (highlighted red if overdue)
- Label badges
- Subtask progress bar (e.g., "3/5 subtasks complete")
- Comment count
- Dependency indicator (lock icon, Business+ plans)

## Moving Tasks Between Columns

Drag a card from one column to another to change its status. The task's status is updated immediately. You can also reorder cards within a column to set visual priority (the order is saved per user).

On mobile (iOS 5.8.2+ and Android 5.8.1+), tap and hold a card, then drag it to the desired column.

## Customizing the Board

### Adding and Removing Columns

1. Go to **Project Settings > Statuses**.
2. Click **+ Add Status** to create a new status (which adds a new column to the board).
3. To remove a column, delete or archive the corresponding status. Tasks in that status must be moved to another status first.

### Reordering Columns

In **Project Settings > Statuses**, drag and drop statuses to change their order. The board reflects this order from left to right.

### Column Limits (WIP Limits)

Set Work-in-Progress (WIP) limits to cap the number of tasks in a column:

1. On the board, click the **three-dot menu** on a column header.
2. Select **Set WIP Limit**.
3. Enter the maximum number of tasks allowed in the column.
4. Click **Save**.

When a column reaches its WIP limit, the column header turns yellow as a visual warning. WIP limits are advisory and do not prevent tasks from being moved into the column.

### Filtering the Board

Use the filter bar above the board to narrow visible tasks:

- **Assignee**: Show only tasks assigned to specific people.
- **Priority**: Filter by priority level.
- **Label**: Show tasks with specific labels.
- **Due date**: Filter by due date range.
- **Custom fields** (Starter+): Filter by custom field values.

Filtered cards that do not match are hidden from the board but remain in the project.

### Grouping Cards

On Starter+ plans, you can group cards within columns by:

- **Assignee**: Cards are grouped under each team member's name within the column.
- **Priority**: Cards are grouped by priority level.
- **Label**: Cards are grouped by label.

To enable grouping, click **Group By** in the board toolbar and select the grouping criterion.

## Adding Tasks from the Board

To create a task directly on the board:

1. Click **+ Add Task** at the bottom of any column.
2. Enter the task title and press Enter.
3. The task is created with the status corresponding to that column.
4. Click the card to open the task detail panel and add more information.

## Board View on Mobile

The mobile app displays the board as horizontal scrollable columns. Swipe left and right to navigate between columns. Tap a card to view details. Drag and drop is supported with a tap-and-hold gesture.

## Troubleshooting

### BOARD_ERR_RENDER

This error occurs when the board fails to render, typically due to a very large number of tasks in a single column (over 500 cards). To resolve:

- Apply filters to reduce the number of visible tasks.
- Archive or move completed tasks out of the column.
- Consider using swimlanes (Business+ plans) to split the board into horizontal sections.

### Cards Not Appearing on the Board

- Verify the task has a status that corresponds to a visible column. If the task's status was deleted, it may be in an unmapped state.
- Check active filters. A filter may be hiding the card.
- If the board was recently loaded offline, some cards may not be cached. Reconnect to sync.

## Related Articles

- Using Swimlanes
- Timeline View and Milestones
- Task Dependencies
