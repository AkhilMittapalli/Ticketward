---
doc_key: kb_email_to_task
doc_type: help_article
title: "Setting Up Email-to-Task"
product_areas:
  - notifications_email
plans_applicable:
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

Email-to-task allows you to create Taskmoor tasks by sending or forwarding emails to a project-specific email address. This feature is available on Business and Enterprise plans. Each project in your workspace can have its own unique inbound email address, and incoming messages are automatically converted into tasks with the email subject as the task title and the email body as the task description.

## Prerequisites

- Your workspace must be on a **Business** or **Enterprise** plan.
- You must be a **Project Admin** or **Workspace Admin** to enable email-to-task for a project.
- Domain verification is recommended (required for Enterprise) to restrict which sender domains can create tasks.

## Enabling Email-to-Task

1. Open the project where you want to enable email-to-task.
2. Click the **gear icon** in the project header to open **Project Settings**.
3. Navigate to **Integrations > Email-to-Task**.
4. Toggle **Enable Email-to-Task** to on.
5. Taskmoor generates a unique email address in the format `project-<shortcode>@inbound.taskmoor.com`. Copy this address.
6. Click **Save**.

Share the generated email address with team members or configure email forwarding rules in your email client to route relevant messages to this address.

## How Incoming Emails Are Processed

When an email arrives at the project inbound address, Taskmoor creates a task with the following mapping:

| Email Field | Task Field |
|---|---|
| Subject line | Task title |
| Body (plain text or HTML) | Task description |
| Attachments | Task attachments (subject to plan file-upload limits) |
| Sender address | Set as the task reporter if the sender is a workspace member |
| CC recipients | Added as task followers if they are workspace members |

### File Upload Limits

Attachments are subject to per-file upload limits based on your plan:

- **Business**: 250 MB per file
- **Enterprise**: 1 GB per file

Attachments exceeding these limits are silently dropped, and a note is added to the task description indicating that one or more attachments could not be uploaded.

## Configuring Sender Restrictions

To prevent unauthorized task creation, you can restrict which email addresses or domains are allowed to send to the project inbound address:

1. In **Project Settings > Integrations > Email-to-Task**, click **Sender Restrictions**.
2. Choose one of the following modes:
   - **Workspace members only** -- Only emails from addresses that match a workspace member's verified email will create tasks.
   - **Allowed domains** -- Specify one or more email domains (e.g., `yourcompany.com`). Only senders from these domains can create tasks.
   - **Open** -- Any sender can create tasks (not recommended for production workspaces).
3. Click **Save**.

On Enterprise plans with domain verification enabled, Taskmoor enforces that the sender's domain matches one of your verified domains by default.

## Default Task Properties

You can configure default values for tasks created via email:

1. In **Project Settings > Integrations > Email-to-Task**, click **Default Task Properties**.
2. Set defaults for:
   - **Status** -- The initial status for new tasks (e.g., "Triage" or "To Do").
   - **Priority** -- Default priority level.
   - **Assignee** -- Optionally auto-assign to a specific team member or leave unassigned.
   - **Labels** -- Apply one or more labels automatically.
3. Click **Save**.

These defaults can be overridden manually after the task is created.

## Troubleshooting

### Emails Not Creating Tasks

- Confirm the email-to-task feature is enabled in project settings.
- Verify that the sender address is not blocked by your sender restriction rules.
- Check that the inbound address is correctly copied -- even a single character difference will cause delivery failure.
- Look for **NOTIF_ERR_BOUNCE** errors in the project activity log, which may indicate Taskmoor's inbound processor could not parse the email.

### Duplicate Tasks from Forwarded Threads

When forwarding email threads, Taskmoor uses the `Message-ID` and `In-Reply-To` headers to detect duplicates. If the same email is forwarded multiple times, only one task is created. However, if the forwarding client strips these headers, duplicates may occur. In that case, consider using a dedicated forwarding rule rather than manual forwarding.

### HTML Formatting Issues

Taskmoor converts HTML email bodies to its internal rich-text format. Complex HTML layouts, embedded images with inline CID references, or heavily styled marketing emails may not render perfectly. For best results, use plain-text emails or simple HTML formatting.

## Related Articles

- Daily Digest Settings
- Automation Rules
