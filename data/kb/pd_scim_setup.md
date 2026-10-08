---
doc_key: pd_scim_setup
doc_type: product_doc
title: "SCIM Technical Setup Guide"
product_areas:
  - sso_identity
plans_applicable:
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-14"
effective_from: "2026-06-17"
effective_to: null
---

## Overview

Taskmoor supports SCIM 2.0 (System for Cross-domain Identity Management) for automated user provisioning and deprovisioning. SCIM integration is available exclusively on the Enterprise plan and enables identity providers to synchronize user accounts with your Taskmoor workspace automatically.

## Supported Identity Providers

Taskmoor has validated SCIM integrations with the following identity providers:

| Identity Provider | Provisioning | Deprovisioning | Group Sync |
|-------------------|:------------:|:--------------:|:----------:|
| Okta | Yes | Yes | Yes |
| Azure AD | Yes | Yes | Yes |
| Google Workspace | Yes | Yes | No |
| OneLogin | Yes | Yes | Yes |

Other SAML 2.0-compliant identity providers that support SCIM 2.0 can be configured manually using the base URL and bearer token.

## SCIM Endpoint Configuration

The SCIM base URL for your workspace is:

```
https://api.taskmoor.com/scim/v2/Users
```

### Generating a SCIM Token

Navigate to **Settings > Security > SCIM Provisioning** in the Taskmoor admin panel. Click **Generate SCIM Token** to create a bearer token. This token is shown only once; store it securely.

SCIM tokens use the prefix `tm_live_` for production and `tm_test_` for sandbox environments.

### Okta Configuration

1. In the Okta Admin Console, navigate to **Applications > Add Application**.
2. Search for "Taskmoor" in the OIN catalog or select **SCIM 2.0 Test App**.
3. Enter the SCIM base URL: `https://api.taskmoor.com/scim/v2/Users`
4. Set the authentication mode to **HTTP Header** and paste your SCIM bearer token.
5. Under **Provisioning > To App**, enable **Create Users**, **Update User Attributes**, and **Deactivate Users**.

### Azure AD Configuration

1. In the Azure Portal, go to **Enterprise Applications > New Application**.
2. Select **Taskmoor** from the gallery or create a non-gallery application.
3. Navigate to **Provisioning > Edit Provisioning**.
4. Set Provisioning Mode to **Automatic**.
5. Enter `https://api.taskmoor.com/scim/v2/Users` as the Tenant URL.
6. Paste the SCIM bearer token in the Secret Token field.
7. Click **Test Connection** to verify connectivity.

## Testing the SCIM Endpoint

Use the sandbox environment to verify your SCIM integration before enabling it in production:

```bash
curl -X GET https://api.taskmoor.com/scim/v2/Users \
  -H "Authorization: Bearer tm_test_scim_token_789" \
  -H "Content-Type: application/scim+json"
```

Expected response:

```json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
  "totalResults": 2,
  "startIndex": 1,
  "itemsPerPage": 100,
  "Resources": [
    {
      "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
      "id": "usr_001",
      "userName": "jdoe@example.com",
      "name": {
        "givenName": "Jane",
        "familyName": "Doe"
      },
      "emails": [
        {
          "value": "jdoe@example.com",
          "primary": true
        }
      ],
      "active": true
    }
  ]
}
```

### Creating a User via SCIM

```bash
curl -X POST https://api.taskmoor.com/scim/v2/Users \
  -H "Authorization: Bearer tm_test_scim_token_789" \
  -H "Content-Type: application/scim+json" \
  -d '{
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
    "userName": "asmith@example.com",
    "name": {
      "givenName": "Alex",
      "familyName": "Smith"
    },
    "emails": [
      {
        "value": "asmith@example.com",
        "primary": true
      }
    ],
    "active": true
  }'
```

### Deactivating a User

```bash
curl -X PATCH https://api.taskmoor.com/scim/v2/Users/usr_002 \
  -H "Authorization: Bearer tm_test_scim_token_789" \
  -H "Content-Type: application/scim+json" \
  -d '{
    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
    "Operations": [
      {
        "op": "replace",
        "path": "active",
        "value": false
      }
    ]
  }'
```

## Error Handling

| Error Code | HTTP Status | Description | Resolution |
|------------|:-----------:|-------------|------------|
| `SCIM_ERR_409` | 409 | User already exists in the workspace | Verify the userName is unique; the email may already be associated with an existing account |
| `SCIM_ERR_422` | 422 | Invalid attribute mapping | Check that required attributes (userName, emails) are present and correctly formatted |
| `API_ERR_401` | 401 | Invalid or revoked SCIM token | Regenerate the token in Settings > Security > SCIM Provisioning |

## Provisioning Logs

Administrators can review SCIM provisioning events in the audit log under **Settings > Security > Audit Log**. Filter by event type `scim.provision` to view all SCIM operations. Each log entry includes the operation type, affected user, source IP, and IdP identifier.
