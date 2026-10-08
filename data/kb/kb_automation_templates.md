---
doc_key: kb_automation_templates
doc_type: help_article
title: "Using Automation Rule Templates"
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

Automation rule templates are pre-built automation configurations that you can apply to any project with one click. Instead of building rules from scratch, templates provide common workflow patterns that can be customized after installation. Rule templates are available on Starter, Business, and Enterprise plans.

## Accessing Rule Templates

1. Navigate to **Project Settings > Automations**.
2. Click **+ New Rule**.
3. Select the **Templates** tab at the top of the rule builder.
4. Browse or search the template library.

## Available Template Categories

Taskmoor provides templates across several categories:

### Task Assignment

- **Auto-assign by label** -- Assigns tasks to a specific team member based on the label applied. For example, tasks labeled "Design" are assigned to your design lead.
- **Round-robin assignment** -- Distributes new tasks evenly across a defined group of team members.
- **Assign on status change** -- Assigns a task to a reviewer when the status changes to "In Review".

### Status Management

- **Auto-close stale tasks** -- Changes the status of tasks to "Closed" if they have been in "Blocked" status for more than 14 days with no activity.
- **Move to In Progress on assignment** -- Automatically changes a task's status from "To Do" to "In Progress" when an assignee is set.
- **Reopen on comment** -- Reopens a completed task if a new comment is added within 48 hours of completion.

### Notifications and Communication

- **Due date reminder** -- Sends a notification to the assignee 3 days before the due date.
- **Overdue alert** -- Notifies the project lead when a task passes its due date without being completed.
- **Assignment notification** -- Sends an email and push notification when a task is assigned.

### Subtask Automation

- **QA checklist** -- Creates a standard set of QA subtasks (e.g., "Unit tests passed", "Code review approved", "Staging verified") when a task moves to "QA" status.
- **Onboarding checklist** -- Adds predefined subtasks to tasks created with the "Onboarding" label.

### Integration-Triggered

- **Slack notification on completion** -- Posts a message to a Slack channel when a task is marked complete (requires Slack integration).
- **GitHub PR linked** -- Updates task status when a linked GitHub pull request is merged (requires GitHub integration, Starter+ plans).

## Installing a Template

1. Click on a template to preview its trigger, conditions, and actions.
2. Click **Use Template**.
3. The rule builder opens with the template's configuration pre-filled.
4. Customize the rule:
   - Update assignee names to match your team members.
   - Adjust status names to match your project's workflow.
   - Modify notification recipients.
   - Change timing parameters (e.g., due date reminder days).
5. Give the rule a descriptive name.
6. Click **Save Rule**.

The template becomes a standard automation rule in your project. Editing the installed rule does not affect the original template.

## Customization Tips

- **Status names must match exactly.** If the template references a status called "In Review" but your project uses "Review", update the rule to match.
- **Custom fields in templates** reference field names. If the template uses a custom field that does not exist in your project, create the field first or remove that condition from the rule.
- **Webhook actions** in templates include a placeholder URL. Replace it with your actual endpoint before activating the rule.

## Creating Your Own Templates (Enterprise)

Enterprise plan administrators can save custom automation rules as workspace templates:

1. Open an existing automation rule.
2. Click the three-dot menu and select **Save as Template**.
3. Enter a template name, description, and category.
4. Click **Save**.

The template appears in the template library for all projects in the workspace. Only workspace admins can create, edit, or delete workspace templates.

## Automation Run Limits with Templates

Template-based rules consume automation runs from the same monthly quota as custom rules:

| Plan | Monthly Automation Runs |
|---|---|
| Starter | 1,000 |
| Business | 10,000 |
| Enterprise | Unlimited |

Monitor your usage under **Workspace Settings > Usage > Automations** to avoid hitting AUTO_ERR_LIMIT.

## Troubleshooting

### Template Actions Not Executing

- Verify that the trigger conditions match your project's actual task data (status names, labels, custom fields).
- Check that the rule is set to **Active**.
- Review the automation run history (Business+ plans) for error details.

### AUTO_ERR_LOOP with Template Rules

If a template-based rule conflicts with another automation rule (e.g., one rule moves a task to "In Progress" on assignment, and another reassigns on status change to "In Progress"), Taskmoor detects the loop and raises AUTO_ERR_LOOP. Deactivate one of the conflicting rules and redesign the workflow to avoid circular triggers.

## Related Articles

- Creating Automation Rules
- Slack Integration Guide
