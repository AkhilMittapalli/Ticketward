---
doc_key: pd_automation_api
doc_type: product_doc
title: "Automation Rules API Reference"
product_areas:
  - automations
plans_applicable:
  - starter
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2027-01-03"
effective_from: "2026-07-07"
effective_to: null
---

## Overview

Taskmoor's Automation Rules API allows you to create, manage, and monitor trigger-based automation rules programmatically. Automation rules execute actions automatically when specified conditions are met within a workspace. Rules are available on Starter plans and above. Business and Enterprise plans include automation run history. Enterprise plans have unlimited automation runs.

## Automation Runs by Plan

| Plan | Monthly Run Limit | Run History |
|------|:-----------------:|:-----------:|
| Starter | 500 | Not available |
| Business | 5,000 | 30-day history |
| Enterprise | Unlimited | 90-day history |

## List Automation Rules

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/automations?project_id=proj_001&limit=20"
```

Response:

```json
{
  "data": [
    {
      "id": "auto_001",
      "name": "Auto-assign on creation",
      "project_id": "proj_001",
      "trigger": {
        "event": "task.created",
        "conditions": [
          {"field": "labels", "operator": "contains", "value": "bug"}
        ]
      },
      "actions": [
        {"type": "assign_user", "user_id": "usr_007"},
        {"type": "set_priority", "value": "high"}
      ],
      "enabled": true,
      "runs_this_month": 42,
      "created_at": "2026-07-07T10:00:00Z"
    }
  ],
  "pagination": {
    "cursor": null,
    "has_more": false,
    "total_count": 1
  }
}
```

## Create an Automation Rule

```bash
curl -X POST https://api.taskmoor.com/v2/automations \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Move completed tasks to Done column",
    "project_id": "proj_001",
    "trigger": {
      "event": "task.status_changed",
      "conditions": [
        {"field": "status", "operator": "eq", "value": "completed"}
      ]
    },
    "actions": [
      {"type": "move_to_column", "column_id": "col_done"},
      {"type": "add_comment", "body": "Task automatically moved to Done."}
    ],
    "enabled": true
  }'
```

### Rule Parameters

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `name` | string | Yes | Human-readable rule name |
| `project_id` | string | Yes | Project the rule applies to |
| `trigger.event` | string | Yes | Event that triggers the rule |
| `trigger.conditions` | array | No | Additional conditions to filter triggers |
| `actions` | array | Yes | Actions to execute when triggered |
| `enabled` | boolean | No | Whether the rule is active (default: `true`) |

### Supported Trigger Events

| Event | Description |
|-------|-------------|
| `task.created` | A new task is created |
| `task.updated` | A task field is modified |
| `task.status_changed` | Task status changes |
| `task.assigned` | Task is assigned to a user |
| `task.due_date_approaching` | Task due date is within 24 hours |
| `comment.created` | A comment is added to a task |

### Supported Actions

| Action Type | Parameters | Description |
|-------------|------------|-------------|
| `assign_user` | `user_id` | Assign a user to the task |
| `set_status` | `value` | Change the task status |
| `set_priority` | `value` | Set task priority (`low`, `medium`, `high`, `urgent`) |
| `add_label` | `label` | Add a label to the task |
| `move_to_column` | `column_id` | Move task to a board column |
| `add_comment` | `body` | Add a comment to the task |
| `send_notification` | `user_ids`, `message` | Notify specified users |

### Condition Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equals | `{"field": "status", "operator": "eq", "value": "todo"}` |
| `ne` | Not equals | `{"field": "priority", "operator": "ne", "value": "low"}` |
| `contains` | Contains value | `{"field": "labels", "operator": "contains", "value": "bug"}` |
| `is_empty` | Field is empty | `{"field": "assignee_id", "operator": "is_empty"}` |
| `is_not_empty` | Field has a value | `{"field": "due_date", "operator": "is_not_empty"}` |

## Update an Automation Rule

```bash
curl -X PATCH https://api.taskmoor.com/v2/automations/auto_001 \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": false
  }'
```

## Delete an Automation Rule

```bash
curl -X DELETE https://api.taskmoor.com/v2/automations/auto_001 \
  -H "Authorization: Bearer tm_test_abc123def456"
```

Returns `204 No Content` on success.

## Error Handling

### AUTO_ERR_LOOP: Automation Loop Detected

When an automation action triggers another automation that feeds back into the first, Taskmoor halts the execution chain and records an `AUTO_ERR_LOOP` error.

```json
{
  "error": {
    "code": "AUTO_ERR_LOOP",
    "message": "Automation loop detected: auto_001 -> auto_003 -> auto_001. Execution halted.",
    "details": {
      "chain": ["auto_001", "auto_003", "auto_001"],
      "halted_at_depth": 3
    }
  }
}
```

Taskmoor limits automation chain depth to 5 levels to prevent runaway loops.

### AUTO_ERR_LIMIT: Monthly Run Limit Reached

When the workspace exceeds its monthly automation run allocation:

```json
{
  "error": {
    "code": "AUTO_ERR_LIMIT",
    "message": "Monthly automation run limit of 5000 reached. Upgrade to Enterprise for unlimited runs.",
    "details": {
      "current_usage": 5000,
      "plan_limit": 5000,
      "resets_at": "2026-08-01T00:00:00Z"
    }
  }
}
```

## Automation Run History (Business+)

View execution history for a specific rule:

```bash
curl -H "Authorization: Bearer tm_test_abc123def456" \
  "https://api.taskmoor.com/v2/automations/auto_001/runs?limit=10"
```

Response includes status, trigger event, actions executed, and any errors encountered.
