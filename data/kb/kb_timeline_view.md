---
doc_key: kb_timeline_view
doc_type: help_article
title: "Using the Timeline View and Milestones"
product_areas:
  - boards_timelines
plans_applicable:
  - starter
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

The timeline view (also known as Gantt view) displays tasks as horizontal bars on a calendar, showing start dates, due dates, and durations at a glance. Milestones mark key dates and deliverables on the timeline. The timeline view is available on Starter, Business, and Enterprise plans. Milestones are available on Business and Enterprise plans.

## Accessing the Timeline View

1. Open a project from the Taskmoor sidebar.
2. Click the **Timeline** tab in the project header.
3. Tasks with both a start date and a due date appear as bars on the timeline. Tasks with only a due date appear as single-point markers.

## Navigating the Timeline

- **Zoom level**: Use the zoom controls in the toolbar to switch between Day, Week, Month, and Quarter views.
- **Scroll**: Click and drag the timeline background to scroll horizontally. Use the vertical scrollbar to navigate the task list.
- **Today marker**: A vertical red line indicates the current date.
- **Date range**: Use the date picker in the toolbar to jump to a specific date range.

## Setting Task Dates for the Timeline

For a task to appear on the timeline, it needs date information:

1. Open the task detail panel.
2. Set the **Start Date** and **Due Date**.
3. The task immediately appears as a bar on the timeline spanning from start to due date.

You can also set dates directly on the timeline:

1. Click on an empty area of the timeline at the desired start date.
2. A new task prompt appears. Enter the task title.
3. Drag the right edge of the bar to set the due date.

To move a task on the timeline, drag the entire bar left or right. To resize a task's duration, drag the left or right edge of the bar.

## Working with Milestones (Business+ Plans)

Milestones are zero-duration markers that represent key dates, deadlines, or deliverables. They appear as diamond shapes on the timeline.

### Creating a Milestone

1. On the timeline, click **+ Add Milestone** in the toolbar.
2. Enter the milestone name (e.g., "Beta Release" or "Client Review").
3. Set the milestone date.
4. Optionally assign the milestone to a team member.
5. Click **Save**.

Alternatively, convert an existing task to a milestone:

1. Open the task detail panel.
2. Click the three-dot menu and select **Convert to Milestone**.
3. The task's due date becomes the milestone date, and the start date is removed.

### Linking Tasks to Milestones

Associate tasks with a milestone to see which work must be completed by that date:

1. Open the milestone by clicking its diamond on the timeline.
2. In the milestone detail panel, click **+ Link Task**.
3. Search for and select tasks.
4. Linked tasks appear grouped under the milestone in the timeline.

## Task Dependencies on the Timeline (Business+ Plans)

On Business and Enterprise plans, dependency arrows are drawn between task bars on the timeline, showing which tasks must complete before others can start. See the Task Dependencies article for details on creating dependencies.

The timeline highlights the **critical path** -- the longest chain of dependent tasks that determines the earliest project completion date. Critical path tasks are visually emphasized with a bold outline.

## Filtering and Grouping

### Filtering the Timeline

Use the filter bar to narrow the timeline view:

- **Assignee**: Show tasks for specific team members.
- **Status**: Show only tasks in certain statuses.
- **Priority**: Filter by priority level.
- **Label**: Filter by label.
- **Milestone**: Show only tasks linked to a specific milestone.

### Grouping Tasks

Group tasks on the timeline by:

- **Assignee**: Tasks are grouped under each team member.
- **Status**: Tasks are grouped by their current status.
- **Label**: Tasks are grouped by label.
- **Milestone**: Tasks are grouped under their linked milestones.

Select the grouping option from the **Group By** dropdown in the toolbar.

## Exporting the Timeline

Export the timeline view as a PDF:

1. Click **Export** in the timeline toolbar.
2. Select **PDF**.
3. Choose the date range and page orientation (landscape is recommended).
4. Click **Download**.

The PDF includes task bars, milestones, dependency arrows, and the today marker.

## Troubleshooting

### Tasks Not Appearing on the Timeline

- Ensure the task has at least a **due date** set. Tasks without any date information do not appear.
- Check that the timeline's date range includes the task's dates. Scroll or zoom out to widen the visible range.
- Verify that active filters are not hiding the task.

### Timeline Performance Is Slow

Large projects with hundreds of tasks can slow down the timeline. To improve performance:

- Apply filters to reduce the number of visible tasks.
- Use a wider zoom level (Month or Quarter) to reduce rendering complexity.
- Archive completed tasks that are no longer relevant.

### BOARD_ERR_RENDER on Timeline

Although this error code references "board," it can also appear when the timeline view fails to render due to data complexity. Reduce the scope by filtering to a subset of tasks or a narrower date range.

## Related Articles

- Task Dependencies
- Using Kanban Boards
- Using Swimlanes
