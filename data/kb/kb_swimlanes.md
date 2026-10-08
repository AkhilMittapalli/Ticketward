---
doc_key: kb_swimlanes
doc_type: help_article
title: "Using Swimlanes on Kanban Boards"
product_areas:
  - boards_timelines
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: ops_lead
review_due_at: "2027-01-28"
effective_from: "2026-08-01"
effective_to: null
---

## Overview

Swimlanes add horizontal rows to your Kanban board, dividing it into parallel sections based on a grouping criterion such as assignee, priority, or label. This makes it easier to visualize work distribution and track progress across categories simultaneously. Swimlanes are available on Business and Enterprise plans.

## Enabling Swimlanes

1. Open a project and navigate to the **Board** view.
2. Click the **Swimlanes** button in the board toolbar (or look for the icon showing horizontal lines).
3. Select the grouping criterion:
   - **Assignee** -- One swimlane per team member, plus an "Unassigned" lane.
   - **Priority** -- Swimlanes for Urgent, High, Medium, Low, and None.
   - **Label** -- One swimlane per label. Tasks with multiple labels appear in the lane of their first label.
   - **Custom Field** (Dropdown or Multi-select) -- One swimlane per dropdown option.
4. The board immediately reorganizes into horizontal sections.

To disable swimlanes, click the **Swimlanes** button again and select **None**.

## Understanding the Swimlane Layout

With swimlanes enabled, the board is structured as a grid:

- **Columns** still represent statuses (To Do, In Progress, Review, Done, etc.).
- **Rows** represent the swimlane categories (assignees, priorities, labels, or custom field values).
- Each cell is the intersection of a status column and a swimlane row.
- Cards appear in the cell matching their status and swimlane grouping.

### Collapsed and Expanded Lanes

Click the chevron icon on a swimlane header to collapse or expand that lane. Collapsed lanes show only the header with a count of tasks inside, saving screen space. This is useful when you want to focus on specific team members or priorities.

### Empty Lanes

By default, lanes with zero tasks are hidden. To show all lanes (including empty ones), toggle **Show Empty Lanes** in the swimlanes dropdown menu. This is useful when you want to see which team members have no tasks assigned.

## Moving Tasks Across Swimlanes

Drag a card vertically from one swimlane to another to change the underlying grouping field. For example:

- **Assignee swimlanes**: Dragging a card from Alice's lane to Bob's lane reassigns the task to Bob.
- **Priority swimlanes**: Dragging from the "Medium" lane to the "High" lane changes the task's priority to High.
- **Label swimlanes**: Dragging between label lanes adds the target label and removes the source label.

You can also drag cards horizontally within a swimlane to change the task's status, the same as on a standard board.

## WIP Limits with Swimlanes

WIP (Work-in-Progress) limits can be set per column, and they apply across all swimlanes. For example, if the "In Progress" column has a WIP limit of 10, the total number of tasks in "In Progress" across all swimlanes is counted toward that limit.

Per-cell WIP limits (limiting tasks in a specific column-swimlane intersection) are not currently supported.

## Swimlane Sorting

Within each swimlane, tasks follow the same sort order as the board. To change the sort order:

1. Click the **Sort** button in the board toolbar.
2. Select the sort criterion (e.g., due date, priority, creation date, custom field).
3. Choose ascending or descending order.
4. The sort applies within each swimlane independently.

## Swimlanes on Mobile

The Taskmoor mobile app (iOS 5.8.2+ and Android 5.8.1+) supports swimlanes in a simplified view:

- Swimlanes appear as collapsible sections.
- Each section shows the swimlane name and task count.
- Tap to expand a swimlane and see its cards arranged by status.
- Drag and drop between swimlanes is supported on mobile.

## Combining Swimlanes with Filters

Filters and swimlanes work together. Applying a filter (e.g., showing only "High" and "Urgent" priority tasks) reduces the visible cards but does not change the swimlane structure. If swimlanes are grouped by assignee, all assignee lanes remain visible but only show filtered tasks.

## Troubleshooting

### BOARD_ERR_RENDER with Swimlanes

Enabling swimlanes on a board with many tasks (over 500) and many swimlane categories (over 20 assignees or labels) can trigger BOARD_ERR_RENDER because the number of cells to render exceeds the performance threshold. To resolve:

- Apply filters to reduce the number of visible tasks.
- Collapse unused swimlanes.
- Choose a swimlane grouping with fewer categories (e.g., Priority has 4-5 lanes versus Assignee which may have 50+).

### Tasks Appearing in the Wrong Swimlane

- If using **label** swimlanes, a task with multiple labels appears in the lane of its first-applied label. To control placement, reorder the task's labels.
- If using **custom field** swimlanes, verify the custom field value is set correctly on the task. Tasks with no value appear in an "Uncategorized" lane.

### Swimlanes Not Available

Swimlanes require a **Business** or **Enterprise** plan. On Starter and Free plans, the swimlanes option does not appear in the board toolbar. Upgrade your plan to access this feature.

## Related Articles

- Using Kanban Boards
- Timeline View and Milestones
- Custom Fields
