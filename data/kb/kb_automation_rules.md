---
doc_key: kb_automation_rules
doc_type: help_article
title: "Creating Automation Rules"
product_areas:
  - automations
plans_applicable:
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

Automation rules in Taskmoor allow you to define trigger-action workflows that execute automatically when specific conditions are met. Automations reduce manual effort by handling repetitive task management operations such as assigning tasks, changing statuses, sending notifications, and more. Automation rules are available on Starter, Business, and Enterprise plans.

## Automation Run Limits

Each plan has a monthly limit on automation rule executions:

| Plan | Monthly Automation Runs |
|---|---|
| Starter | 1,000 |
| Business | 10,000 |
| Enterprise | Unlimited |

When you reach your monthly limit, automation rules stop executing until the next billing cycle. You receive a warning notification at 80% and 100% of your limit.

## Creating an Automation Rule

1. Navigate to **Project Settings > Automations** (or **Workspace Settings > Automations** for workspace-wide rules on Business+ plans).
2. Click **+ New Rule**.
3. Configure the rule with a **Trigger**, optional **Conditions**, and one or more **Actions**.

### Step 1: Choose a Trigger

Triggers define the event that starts the automation. Available triggers include:

- **Task created** -- Fires when a new task is added to the project.
- **Status changed** -- Fires when a task's status changes (optionally specify from/to statuses).
- **Assignee changed** -- Fires when a task is assigned or reassigned.
- **Due date reached** -- Fires when a task's due date arrives.
- **Due date approaching** -- Fires a configurable number of days before the due date (1, 3, 5, or 7 days).
- **Comment added** -- Fires when a comment is posted on a task.
- **Custom field changed** -- Fires when a specific custom field value changes (Starter+).
- **Task moved to project** -- Fires when a task is moved from another project.

### Step 2: Add Conditions (Optional)

Conditions narrow when the rule fires. You can add multiple conditions using AND/OR logic:

- Task status is/is not a specific value
- Task priority is/is not a specific level
- Task has/does not have a specific label
- Assignee is/is not a specific member
- Custom field equals/does not equal a value

### Step 3: Define Actions

Actions are what happens when the trigger fires and conditions are met. You can chain multiple actions:

- **Change status** -- Set the task to a specified status.
- **Assign to** -- Assign the task to a specific member, the project lead, or round-robin among a group.
- **Set priority** -- Change the task's priority level.
- **Add label** -- Apply one or more labels.
- **Add comment** -- Post an automated comment (supports variables like `{task_title}`, `{assignee}`).
- **Send notification** -- Send an email or push notification to specified members.
- **Create subtask** -- Automatically add a subtask with a predefined title.
- **Set due date** -- Set a due date relative to the trigger event (e.g., 7 days from creation).
- **Move to project** -- Move the task to a different project.
- **Trigger webhook** -- Send a POST request to an external URL (Business+ plans).

### Step 4: Name and Save

1. Give your rule a descriptive name (e.g., "Auto-assign bugs to QA lead").
2. Toggle the rule **Active** or leave it inactive for testing.
3. Click **Save Rule**.

## Testing Automation Rules

Before activating a rule, test it:

1. Set the rule to **Inactive**.
2. Click **Test Rule** in the rule editor.
3. Select an existing task to simulate the trigger against.
4. Taskmoor shows what actions would execute without actually performing them.
5. Review the simulation results and adjust conditions or actions as needed.

## Monitoring Automation Runs

### Run History (Business+ Plans)

Business and Enterprise plans include automation run history:

1. Go to **Project Settings > Automations > Run History**.
2. View a log of every automation execution, including timestamp, trigger event, conditions evaluated, actions taken, and success/failure status.

### Error Handling

- **AUTO_ERR_LOOP**: This error occurs when an automation action triggers another automation, which in turn triggers the first, creating an infinite loop. Taskmoor detects loops after 5 iterations and halts execution. Review your rules to break the circular dependency.
- **AUTO_ERR_LIMIT**: This error indicates you have reached your monthly automation run limit. Upgrade your plan or wait for the next billing cycle.

## Disabling or Deleting Rules

- To disable a rule temporarily, toggle it to **Inactive** in the automation rules list.
- To delete a rule permanently, click the three-dot menu and select **Delete**. Deletion is irreversible and removes the rule from run history.

## Related Articles

- Using Automation Rule Templates
- Creating Dashboards
- Webhook Integration
