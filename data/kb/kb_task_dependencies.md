---
doc_key: kb_task_dependencies
doc_type: help_article
title: "Setting Up Task Dependencies"
product_areas:
  - projects_tasks
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

Task dependencies in Taskmoor define relationships between tasks where one task must be completed before another can begin. Dependencies help teams enforce execution order, visualize critical paths on the timeline, and prevent work from starting prematurely. Task dependencies are available on Business and Enterprise plans.

## Types of Dependencies

Taskmoor supports the following dependency types:

| Dependency Type | Meaning |
|---|---|
| **Finish-to-Start (FS)** | Task B cannot start until Task A is finished. This is the most common type. |
| **Start-to-Start (SS)** | Task B cannot start until Task A has started. |
| **Finish-to-Finish (FF)** | Task B cannot finish until Task A is finished. |
| **Start-to-Finish (SF)** | Task B cannot finish until Task A has started (rarely used). |

The default dependency type is Finish-to-Start.

## Creating a Dependency

### From the Task Detail View

1. Open the dependent task (the task that must wait).
2. In the task detail panel, scroll to the **Dependencies** section.
3. Click **+ Add Dependency**.
4. Search for and select the prerequisite task (the task that must complete first).
5. Choose the dependency type from the dropdown (default: Finish-to-Start).
6. Click **Save**.

### From the Timeline View

1. Open the project's **Timeline** view (requires Starter+ plan for timeline, Business+ for dependencies).
2. Hover over a task bar to reveal the dependency handle (a small circle on the right edge).
3. Click and drag from the handle of the prerequisite task to the dependent task.
4. A dependency arrow is drawn between the two task bars.
5. To change the dependency type, click the arrow and select from the dropdown.

### From the Board View

Dependencies are displayed as subtle connector lines on the Kanban board when both tasks are visible. To create dependencies from the board, open the task detail view and follow the steps above.

## Viewing Dependencies

### Task Detail Panel

The Dependencies section in the task detail panel shows:

- **Blocked by**: Tasks that must complete before this task can start.
- **Blocking**: Tasks that are waiting on this task.

Each listed task shows its current status, allowing you to quickly assess whether blockers are resolved.

### Timeline View

Dependencies are displayed as arrows connecting task bars. The timeline automatically adjusts the visual layout to show the critical path (the longest sequence of dependent tasks).

### Dependency Indicators on Task Lists

In List View, tasks with unresolved dependencies display a small lock icon. Hovering over the icon shows the blocking task(s) and their statuses.

## Dependency Enforcement

By default, dependencies are **advisory**: they provide visual warnings but do not prevent users from changing a task's status. Project Admins can enable strict enforcement:

1. Go to **Project Settings > Task Settings**.
2. Toggle **Enforce Dependencies** to on.
3. Click **Save**.

When enforcement is enabled:

- Users cannot move a task to "In Progress" or "Done" if its prerequisite tasks are not complete.
- An error message explains which prerequisites must be resolved first.
- Workspace Admins can override enforcement on a per-task basis.

## Troubleshooting

### TASK_ERR_DEP_CYCLE

This error occurs when you attempt to create a dependency that would form a circular chain (e.g., Task A depends on Task B, which depends on Task C, which depends on Task A). Taskmoor rejects the dependency and displays TASK_ERR_DEP_CYCLE.

To resolve:

1. Review the existing dependency chain for the tasks involved.
2. Remove or restructure one of the dependencies to break the cycle.
3. Use the timeline view to visualize the dependency graph and identify where the loop exists.

### Dependencies Not Visible on Timeline

- Ensure you are on a **Business** or **Enterprise** plan. The Timeline view on Starter plans displays tasks but does not support dependency arrows.
- Both the prerequisite and dependent tasks must have due dates set to appear on the timeline.

### Task Appears Blocked Incorrectly

If a task shows as blocked but you believe the prerequisite is complete, check:

- The prerequisite task's status. It must be in a status mapped to the "Done" category in **Project Settings > Statuses**.
- If the dependency type is not Finish-to-Start, the blocking condition may differ. Review the dependency type in the task detail panel.

## Related Articles

- Timeline View and Milestones
- Kanban Boards
- Creating Automation Rules
