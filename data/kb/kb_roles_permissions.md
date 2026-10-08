---
doc_key: kb_roles_permissions
doc_type: help_article
title: "Roles and Permissions Overview"
product_areas:
  - user_admin_permissions
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

Taskmoor uses a role-based access control system to manage what users can see and do within a workspace. Each user is assigned a workspace-level role that determines their global permissions. Additionally, project-level roles can further refine access within individual projects.

Roles and permissions are available on all plans.

## Workspace-Level Roles

Taskmoor provides four workspace-level roles, listed from most to least privileged:

### Workspace Owner

- Full control over the workspace, including billing, security settings, and member management.
- Can delete the workspace.
- Can transfer workspace ownership to another member.
- Retains password login access even when SSO is enforced (Business and Enterprise plans).
- Every workspace must have at least one Workspace Owner.

### Admin

- Can manage members: invite, remove, and change roles (except Workspace Owner).
- Can manage workspace settings, including integrations, automations, and security preferences.
- Cannot access billing settings or delete the workspace.
- Can create and archive projects.

### Member

- Can create projects and tasks.
- Can view all projects they have access to.
- Can edit tasks assigned to them and tasks in projects they belong to.
- Cannot manage workspace settings or other members.
- This is the default role for newly invited users.

### Limited Member

- Can view and interact with tasks assigned to them only.
- Cannot create new projects.
- Can create tasks only in projects where they have been explicitly added.
- Ideal for external contractors or part-time staff who need minimal access.

## Project-Level Roles

Within individual projects, users can be assigned project-specific roles that override some workspace-level permissions for that project:

### Project Admin

- Full control over the project, including settings, member management, and deletion.
- Can add or remove members and guests from the project.
- Automatically assigned to the project creator.

### Project Member

- Can create, edit, and complete tasks within the project.
- Can comment on tasks and upload attachments.
- Cannot change project settings or manage project membership.

### Project Viewer

- Read-only access to the project.
- Can view tasks, comments, and attachments but cannot make changes.
- Useful for stakeholders who need visibility without edit rights.

## Permissions Matrix

| Action | Owner | Admin | Member | Limited Member |
|---|---|---|---|---|
| Manage billing | Yes | No | No | No |
| Manage workspace security | Yes | Yes | No | No |
| Invite/remove members | Yes | Yes | No | No |
| Change member roles | Yes | Yes (not Owner) | No | No |
| Create projects | Yes | Yes | Yes | No |
| Archive/delete projects | Yes | Yes | Project Admin | No |
| Create tasks | Yes | Yes | Yes | Assigned projects |
| Edit any task | Yes | Yes | Own projects | Assigned tasks |
| View all projects | Yes | Yes | Accessible | Assigned only |
| Manage integrations | Yes | Yes | No | No |
| Manage automations | Yes | Yes | Project Admin | No |
| View audit log (Enterprise) | Yes | Yes | No | No |
| Generate API tokens (Starter+) | Yes | Yes | Yes | No |
| View dashboards (Starter+) | Yes | Yes | Yes | No |

## Changing a User's Role

1. Go to **Settings > Members**.
2. Find the user whose role you want to change.
3. Click the role dropdown next to their name.
4. Select the new role.
5. Click **Save**.

Only Workspace Owners can promote someone to Workspace Owner or demote another Owner. Admins can change roles for Members and Limited Members but cannot modify other Admins or Owners.

## Role Restrictions by Plan

The role system is available on all plans, but certain capabilities tied to roles differ by plan:

- **Free plan**: Up to 5 seats. All workspace roles available, but plan-limited features (e.g., custom fields, dashboards) are not accessible regardless of role.
- **Starter plan**: Up to 50 seats. Guest access is available. API token generation requires the Member role or higher.
- **Business plan**: Up to 500 seats. SAML SSO, audit log access restricted to Owners and Admins.
- **Enterprise plan**: Unlimited seats. Full audit log, SCIM provisioning, and all security features.

## Best Practices

- **Limit the number of Workspace Owners.** One or two Owners is sufficient for most organizations. Owners have access to billing and can delete the workspace.
- **Use Admin for IT and team leads** who need to manage members and settings but should not have billing access.
- **Use Limited Member for contractors** or external collaborators who should only see tasks assigned to them.
- **Use Project Viewer for executives or stakeholders** who need to monitor progress without editing tasks.
- **Review roles quarterly** to ensure departing members or role changes are reflected in Taskmoor.

## Troubleshooting

### PERM_ERR_403 -- No Access

The user does not have the required permission for the action they attempted. Check the permissions matrix above and verify the user's workspace role and project role. If the user should have access, ask a Workspace Owner or Admin to update their role.

### Cannot find the option to change roles

Only Workspace Owners and Admins see the role management controls in **Settings > Members**. If you are a Member or Limited Member, contact your Workspace Owner or Admin.
