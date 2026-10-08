---
doc_key: kb_recurring_tasks
doc_type: help_article
title: "Setting Up Recurring Tasks"
product_areas:
  - projects_tasks
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

Recurring tasks in Taskmoor allow you to automatically create new task instances on a set schedule. This is useful for repetitive work such as weekly status reports, monthly reviews, daily stand-up agendas, or quarterly audits. Recurring tasks are available on all plans, including Free.

## Prerequisites

- You must have **Member** or higher permissions in the project where the recurring task will be created.
- The project must be active (not archived).

## Creating a Recurring Task

### Step 1: Create or Open a Task

1. Open the project where you want the recurring task.
2. Click **+ New Task** to create a new task, or open an existing task you want to make recurring.

### Step 2: Set the Recurrence

1. In the task detail panel, click the **Due Date** field.
2. Select a due date for the first occurrence.
3. Click the **Repeat** icon (circular arrow) next to the due date.
4. Choose a recurrence pattern:
   - **Daily** -- creates a new task every day or every N days.
   - **Weekly** -- creates a new task on selected days of the week (e.g., every Monday and Wednesday).
   - **Monthly** -- creates a new task on a specific day of the month or on a relative day (e.g., the first Monday of each month).
   - **Yearly** -- creates a new task on a specific date each year.
   - **Custom** -- set an interval such as every 2 weeks or every 3 months.
5. Optionally, set an **End condition**:
   - **Never** -- the task recurs indefinitely.
   - **After N occurrences** -- the task stops recurring after a set number of instances.
   - **On date** -- the task stops recurring after a specific date.
6. Click **Save**.

### Step 3: Configure What Gets Copied

When a recurring task creates a new instance, the following are copied from the original:

- Task title and description
- Assignee
- Priority level
- Labels and tags
- Subtasks (if any)
- Custom fields (Starter plan and above)
- Checklists

Attachments and comments are **not** copied to new instances.

## Managing Recurring Tasks

### Viewing Recurring Tasks

Recurring tasks display a circular arrow icon next to the task title in list and board views. To see all recurring tasks in a project:

1. Open the project.
2. Click **Filter** in the toolbar.
3. Select **Recurring** under the Task Type filter.

### Editing the Recurrence Pattern

1. Open the recurring task.
2. Click the recurrence indicator next to the due date.
3. Modify the pattern, interval, or end condition.
4. Click **Save**.

Changes to the recurrence pattern only affect future instances. Previously created instances remain unchanged.

### Stopping Recurrence

To stop a task from recurring:

1. Open the recurring task.
2. Click the recurrence indicator.
3. Select **Remove Recurrence**.
4. Confirm the action.

Existing instances already created are not deleted. Only future instances are prevented.

### Completing a Recurring Instance

When you mark a recurring task as complete, Taskmoor automatically creates the next instance according to the recurrence pattern. The new instance:

- Gets a due date calculated from the recurrence schedule.
- Appears in the same project and section as the original.
- Carries over all copied fields listed above.

If you complete a recurring task after its due date, the next instance is still based on the original schedule, not the completion date. For example, if a weekly task due on Monday is completed on Wednesday, the next instance is still due the following Monday.

## Tips and Best Practices

- **Use task templates on Starter and above:** If your recurring task needs consistent structure, create a task template first, then set it as the base for your recurring task. The template fields populate each new instance automatically.
- **Assign to roles, not individuals:** If team members rotate, consider leaving the assignee blank and using project-level assignment rules.
- **Monitor overdue recurrences:** If a recurring instance is not completed before the next one is created, both instances will exist. Use the Overdue filter to track these.
- **Subtask behavior:** Subtasks are recreated as incomplete in each new instance regardless of their status in the previous instance.

## Troubleshooting

### New instances are not being created

- Verify the recurrence has not reached its end condition (occurrence limit or end date).
- Ensure the project is not archived. Recurring tasks in archived projects are paused.
- Check that the original recurring task has not been deleted. Deleting the original stops all future instances.

### Recurrence creates duplicate tasks

- This can happen if the task is completed and then reopened. Reopening a completed recurring task does not cancel the next instance that was already created. Delete the duplicate manually if needed.
