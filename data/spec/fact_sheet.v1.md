<!--
fact_sheet.v1 - the only Taskmoor product facts a generator prompt may contain (spec §3, §9.1;
ERPROT synthetic-data-generation D6). Facts only: no knowledge-base article text and no example
tickets. The KB written later in P1 (data/kb/) must use these same values.
tw_ml.datagen.factsheet parses the tables below: keep the headings and column names.
This comment block is stripped before the sheet is placed in a prompt.
-->
# Taskmoor fact sheet (v1)

Taskmoor is a fictional B2B project-management SaaS. It is not affiliated with any real company.
All prices are fictional.

## Plans

| plan | price_per_seat_month | seats_max | support | frt_multiplier | sso | scim | uptime_sla |
|---|---|---|---|---|---|---|---|
| free | $0 | 5 | community forum and email, best effort | 2 | no | no | none |
| starter | $8 | 50 | email | 1.5 | no | no | 99.5% |
| business | $16 | 500 | email and chat, priority queue | 1 | saml | no | 99.9% |
| enterprise | custom contract | unlimited | 24/7 with a named customer success manager | 0.5 | saml | yes | 99.95% with service credits |

## Response targets

Business plan base; multiply by the plan's frt_multiplier.

| priority | first_response | resolution_target |
|---|---|---|
| urgent | 1 hour | 8 hours |
| high | 4 hours | 1 business day |
| normal | 1 business day | 3 business days |
| low | 2 business days | 5 business days |

## Identity providers

| idp | saml_idp_value | aliases | plans |
|---|---|---|---|
| Okta | okta | Okta | business, enterprise |
| Azure AD | azure_ad | Azure AD; Microsoft Entra ID; Entra ID; Azure Active Directory | business, enterprise |
| Google Workspace | google | Google Workspace; Google | business, enterprise |
| OneLogin | onelogin | OneLogin | enterprise |
| other SAML 2.0 provider | other | SAML 2.0 | enterprise |

## Product areas

| product_area | display_name | covers |
|---|---|---|
| projects_tasks | Projects and tasks | projects, tasks, subtasks, custom fields, dependencies |
| boards_timelines | Boards and timelines | kanban boards, timeline view, milestones, swimlanes |
| sso_identity | SSO and identity | SAML single sign-on, SCIM provisioning, domain verification |
| user_admin_permissions | Users, admin and permissions | members, roles, guests, invitations, passwords, two-factor authentication |
| billing_subscriptions | Billing and subscriptions | plans, seats, invoices, payment methods, renewals |
| integrations_api | Integrations and API | REST API, webhooks, API tokens, third-party integrations |
| notifications_email | Notifications and email | email notifications, digests, mentions, email-to-task |
| mobile_apps | Mobile apps | iOS and Android apps, push notifications, offline mode |
| reporting_analytics | Reporting and analytics | dashboards, workload and time reports, scheduled exports |
| automations | Automations | automation rules, triggers, actions, run history |
| data_import_export | Data import and export | CSV and Excel import, workspace export, PDF export |
| platform_availability | Platform availability | web app availability, performance, regions, status page |

## Features

| feature | product_area | plans |
|---|---|---|
| Subtasks | projects_tasks | all |
| Recurring tasks | projects_tasks | all |
| Task templates | projects_tasks | starter, business, enterprise |
| Custom fields | projects_tasks | starter, business, enterprise |
| Task dependencies | projects_tasks | business, enterprise |
| Kanban boards | boards_timelines | all |
| Timeline view | boards_timelines | starter, business, enterprise |
| Milestones | boards_timelines | business, enterprise |
| Swimlanes | boards_timelines | business, enterprise |
| SAML SSO | sso_identity | business, enterprise |
| Just-in-time provisioning | sso_identity | business, enterprise |
| Domain verification | sso_identity | business, enterprise |
| SCIM provisioning | sso_identity | enterprise |
| Roles and permissions | user_admin_permissions | all |
| Guest access | user_admin_permissions | starter, business, enterprise |
| Member invitations | user_admin_permissions | all |
| Two-factor authentication | user_admin_permissions | all |
| Audit log | user_admin_permissions | enterprise |
| Seat management | billing_subscriptions | all |
| Invoices and receipts | billing_subscriptions | all |
| Payment methods | billing_subscriptions | all |
| Annual billing | billing_subscriptions | starter, business, enterprise |
| REST API v2 | integrations_api | starter, business, enterprise |
| Webhooks | integrations_api | business, enterprise |
| API tokens | integrations_api | starter, business, enterprise |
| Email notifications | notifications_email | all |
| Daily digest | notifications_email | all |
| Email-to-task | notifications_email | business, enterprise |
| Mobile offline mode | mobile_apps | all |
| Push notifications | mobile_apps | all |
| Dashboards | reporting_analytics | starter, business, enterprise |
| Workload report | reporting_analytics | business, enterprise |
| Time tracking reports | reporting_analytics | business, enterprise |
| Scheduled report exports | reporting_analytics | enterprise |
| Automation rules | automations | starter, business, enterprise |
| Rule templates | automations | starter, business, enterprise |
| Automation run history | automations | business, enterprise |
| CSV import | data_import_export | all |
| Excel import | data_import_export | starter, business, enterprise |
| Workspace export | data_import_export | business, enterprise |
| PDF export | data_import_export | all |
| Status page | platform_availability | all |

## Integrations

| integration | product_area | plans |
|---|---|---|
| Slack | integrations_api | all |
| Microsoft Teams | integrations_api | starter, business, enterprise |
| GitHub | integrations_api | starter, business, enterprise |
| GitLab | integrations_api | business, enterprise |
| Google Calendar | integrations_api | all |
| Outlook Calendar | integrations_api | all |
| Google Drive | integrations_api | all |
| Zapier | integrations_api | starter, business, enterprise |
| Salesforce | integrations_api | enterprise |

## Limits

| plan | automation_runs_per_month | api_requests_per_minute | file_upload_limit |
|---|---|---|---|
| free | 100 | no API access | 10 MB |
| starter | 1,000 | 300 | 100 MB |
| business | 10,000 | 600 | 250 MB |
| enterprise | unlimited | 1,200 | 1 GB |

## API

| item | value |
|---|---|
| base_path | /v2 |
| endpoints | /v2/tasks, /v2/projects, /v2/boards, /v2/comments, /v2/webhooks, /v2/users, /v2/time-entries, /v2/exports |
| scim_endpoint | /scim/v2/Users |
| rate_limit | per API token, see Limits; exceeding it returns HTTP 429 |
| token_prefixes | tm_live_ (production), tm_test_ (sandbox) |

## Error codes

| code | product_area | shown_message |
|---|---|---|
| SAML_ERR_302 | sso_identity | SAML response signature invalid |
| SAML_ERR_401 | sso_identity | User not assigned to application |
| SAML_ERR_408 | sso_identity | SAML assertion expired |
| SAML_ERR_415 | sso_identity | Unsupported NameID format |
| SCIM_ERR_409 | sso_identity | User already exists |
| SCIM_ERR_422 | sso_identity | Invalid attribute mapping |
| AUTH_ERR_LOCKED | user_admin_permissions | Account temporarily locked |
| AUTH_ERR_MFA_TIMEOUT | user_admin_permissions | Verification code expired |
| AUTH_ERR_INVITE_EXPIRED | user_admin_permissions | Invitation link expired |
| PERM_ERR_403 | user_admin_permissions | No access to this project |
| PAY_ERR_DECLINED | billing_subscriptions | Card declined by issuer |
| PAY_ERR_3DS | billing_subscriptions | Card authentication failed |
| PAY_ERR_EXPIRED | billing_subscriptions | Card expired |
| BILL_ERR_SEAT_LIMIT | billing_subscriptions | Seat limit reached |
| API_ERR_401 | integrations_api | Invalid or revoked token |
| API_ERR_429 | integrations_api | Rate limit exceeded |
| HOOK_ERR_TIMEOUT | integrations_api | Webhook endpoint timed out |
| HOOK_ERR_410 | integrations_api | Webhook endpoint gone |
| SYNC_ERR_CALENDAR | integrations_api | Calendar sync expired |
| NOTIF_ERR_BOUNCE | notifications_email | Email address bounced |
| NOTIF_ERR_DIGEST | notifications_email | Digest could not be generated |
| MOB_ERR_SESSION | mobile_apps | Session expired |
| MOB_ERR_SYNC | mobile_apps | Offline changes not synced |
| RPT_ERR_TIMEOUT | reporting_analytics | Report timed out |
| AUTO_ERR_LOOP | automations | Automation loop detected |
| AUTO_ERR_LIMIT | automations | Monthly run limit reached |
| IMP_ERR_ENCODING | data_import_export | Unsupported file encoding |
| IMP_ERR_ROWS | data_import_export | Row limit exceeded |
| EXP_ERR_SIZE | data_import_export | Export too large |
| TASK_ERR_DEP_CYCLE | projects_tasks | Dependency cycle detected |
| BOARD_ERR_RENDER | boards_timelines | Board failed to load |
| PLAT_ERR_503 | platform_availability | Service temporarily unavailable |
| PLAT_ERR_504 | platform_availability | Gateway timeout |

## HTTP statuses

| status | product_area | meaning |
|---|---|---|
| HTTP 401 | integrations_api | missing or invalid token |
| HTTP 403 | integrations_api | token lacks permission |
| HTTP 404 | integrations_api | resource not found |
| HTTP 409 | integrations_api | conflicting update |
| HTTP 422 | integrations_api | invalid request body |
| HTTP 429 | integrations_api | rate limit exceeded |
| HTTP 500 | platform_availability | internal error |
| HTTP 502 | platform_availability | bad gateway |
| HTTP 503 | platform_availability | service unavailable |
| HTTP 504 | platform_availability | gateway timeout |

## Regions

| region | display_name | data_location |
|---|---|---|
| us | US | United States |
| eu | EU | European Union |
| apac | APAC | Asia-Pacific |

## Apps

| platform | current_version | previous_version |
|---|---|---|
| web | continuous delivery | none |
| ios | 5.8.2 | 5.7.4 |
| android | 5.8.1 | 5.7.3 |
| desktop | 3.2.0 | 3.1.9 |

## Identifiers

| identifier | format |
|---|---|
| account id | acct_ followed by letters and digits |
| workspace id | ws_ followed by 8 hexadecimal characters |
| invoice number | INV- followed by one letter and 6 digits |
