---
doc_key: kb_api_tokens
doc_type: help_article
title: "Creating and Managing API Tokens"
product_areas:
  - integrations_api
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

API tokens authenticate requests to the Taskmoor REST API v2. Each token is tied to a specific user account and inherits that user's workspace permissions. This article explains how to create, manage, and secure API tokens.

API tokens are available on the **Starter**, **Business**, and **Enterprise** plans.

## Prerequisites

- You must have the **Member** role or higher in your Taskmoor workspace.
- Your workspace must be on the Starter, Business, or Enterprise plan.
- Limited Members cannot generate API tokens.

## Token Types

Taskmoor issues two types of API tokens, distinguished by their prefix:

| Token Type | Prefix | Purpose |
|---|---|---|
| Live token | `tm_live_` | Used for production API calls that read and modify real workspace data. |
| Test token | `tm_test_` | Used for development and testing. Test tokens operate on a sandbox copy of your workspace data. Changes made with test tokens do not affect production data. |

## Creating an API Token

1. Log in to Taskmoor.
2. Click your avatar in the bottom-left corner and select **Account Settings**.
3. Go to the **API Tokens** tab.
4. Click **Generate New Token**.
5. Enter a descriptive **Token Name** (e.g., "CI Pipeline", "Reporting Script", "Development Testing").
6. Select the **Token Type**: Live or Test.
7. Set the **Expiration** (optional):
   - No expiration (default)
   - 30 days
   - 90 days
   - 1 year
8. Click **Generate**.
9. The token is displayed once. Copy it immediately and store it securely. You cannot view the full token again after closing the dialog.

## Using API Tokens

Include the token in the `Authorization` header of your API requests:

```
Authorization: Bearer tm_live_your_token_here
```

All API requests are made against the base URL `/v2`. For example:

```
GET /v2/projects
Authorization: Bearer tm_live_your_token_here
```

See the REST API getting started article for detailed endpoint documentation.

## Rate Limits

API rate limits vary by plan:

| Plan | Rate Limit |
|---|---|
| Free | No API access |
| Starter | 300 requests/minute |
| Business | 600 requests/minute |
| Enterprise | 1,200 requests/minute |

When you exceed the rate limit, the API returns error **API_ERR_429** (rate limit exceeded) with a `Retry-After` header indicating how many seconds to wait before retrying.

## Managing Existing Tokens

### Viewing Tokens

1. Go to **Account Settings > API Tokens**.
2. The list shows all your active tokens with:
   - Token name
   - Token type (Live/Test)
   - Created date
   - Last used date
   - Expiration date (if set)
   - First 8 characters of the token for identification

### Revoking a Token

To revoke (permanently delete) a token:

1. Go to **Account Settings > API Tokens**.
2. Find the token to revoke.
3. Click the options menu and select **Revoke**.
4. Confirm the revocation.

Revoked tokens are immediately invalidated. Any API requests using the revoked token will receive error **API_ERR_401** (invalid token).

Revocation cannot be undone. If you need API access again, generate a new token.

### Rotating Tokens

For security, rotate your API tokens periodically:

1. Generate a new token with the same name and type.
2. Update your applications and scripts to use the new token.
3. Verify the new token works correctly.
4. Revoke the old token.

This approach avoids downtime, as both the old and new tokens are valid simultaneously until you revoke the old one.

## Security Best Practices

- **Never share tokens in code repositories.** Use environment variables or secret management tools to store tokens.
- **Use test tokens for development.** Test tokens (`tm_test_`) operate on sandbox data, so accidental calls during development do not affect production.
- **Set expiration dates** for tokens used in temporary scripts or integrations.
- **Use separate tokens** for each application or service. This way, revoking one token does not break other integrations.
- **Monitor usage.** Check the "Last used" column regularly. If a token has not been used in a long time, consider revoking it.
- **Audit token activity** (Enterprise plan). The audit log records token creation and revocation events.

## Troubleshooting

### API_ERR_401 -- Invalid Token

- The token may have been revoked. Check **Account Settings > API Tokens** for active tokens.
- The token may have expired. Generate a new one.
- Verify the token is correctly formatted with the `Bearer ` prefix in the Authorization header (note the space after "Bearer").
- Ensure you are using a Live token (`tm_live_`) for production endpoints. Test tokens have limited scope.

### API_ERR_429 -- Rate Limit Exceeded

- You have exceeded your plan's rate limit. Implement exponential backoff in your application.
- Check the `Retry-After` response header for the recommended wait time.
- If you consistently hit the rate limit, consider upgrading to a higher plan for increased limits.

### Token not appearing after generation

Clear your browser cache and reload the API Tokens page. If the token still does not appear, try generating it in an incognito window.
