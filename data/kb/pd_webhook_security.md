---
doc_key: pd_webhook_security
doc_type: product_doc
title: "Webhook Security: HMAC Signatures and Verification"
product_areas:
  - integrations_api
plans_applicable:
  - business
  - enterprise
version: 1
approval_status: approved
owner: engineering
review_due_at: "2026-12-28"
effective_from: "2026-07-01"
effective_to: null
---

## Overview

Taskmoor signs every webhook delivery with an HMAC-SHA256 signature, allowing your endpoint to verify that payloads originate from Taskmoor and have not been tampered with in transit. Webhook signature verification is strongly recommended for all production integrations.

## Signature Header

Each webhook delivery includes the `X-Taskmoor-Signature` header, which contains the HMAC-SHA256 signature of the request body:

```
X-Taskmoor-Signature: sha256=5d41402abc4b2a76b9719d911017c592ae1d3f7a891bc1e2c9b8f0e2a7c9f801
```

The header value has the format `sha256={hex_digest}`, where the digest is computed from the raw request body using your webhook's shared secret as the HMAC key.

## How Signing Works

When Taskmoor delivers a webhook, the following process occurs:

1. Taskmoor serializes the event payload as a JSON string (the raw request body).
2. Taskmoor computes `HMAC-SHA256(webhook_secret, raw_body)`.
3. The resulting hex digest is prepended with `sha256=` and sent in the `X-Taskmoor-Signature` header.

The `webhook_secret` is the `secret` value you provided when registering the webhook.

## Verifying Signatures

### Step 1: Extract the Signature

Read the `X-Taskmoor-Signature` header from the incoming request.

### Step 2: Compute the Expected Signature

Compute the HMAC-SHA256 of the raw request body using your stored webhook secret.

### Step 3: Compare Using Constant-Time Comparison

Use a timing-safe comparison function to prevent timing attacks.

### Python Example

```python
import hmac
import hashlib

def verify_webhook(payload_body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False

    received_sig = signature_header[7:]
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(received_sig, expected_sig)
```

### Node.js Example

```javascript
const crypto = require("crypto");

function verifyWebhook(payloadBody, signatureHeader, secret) {
  if (!signatureHeader.startsWith("sha256=")) {
    return false;
  }

  const receivedSig = signatureHeader.slice(7);
  const expectedSig = crypto
    .createHmac("sha256", secret)
    .update(payloadBody)
    .digest("hex");

  return crypto.timingSafeEqual(
    Buffer.from(receivedSig, "hex"),
    Buffer.from(expectedSig, "hex")
  );
}
```

### Go Example

```go
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "strings"
)

func verifyWebhook(body []byte, signatureHeader, secret string) bool {
    if !strings.HasPrefix(signatureHeader, "sha256=") {
        return false
    }
    receivedSig := signatureHeader[7:]
    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write(body)
    expectedSig := hex.EncodeToString(mac.Sum(nil))
    return hmac.Equal([]byte(receivedSig), []byte(expectedSig))
}
```

## Timestamp Validation

In addition to the HMAC signature, Taskmoor includes a `X-Taskmoor-Timestamp` header with the Unix timestamp of the delivery:

```
X-Taskmoor-Timestamp: 1719849600
```

To prevent replay attacks, verify that the timestamp is within an acceptable window (recommended: 5 minutes):

```python
import time

def verify_timestamp(timestamp_header: str, tolerance_seconds: int = 300) -> bool:
    delivery_time = int(timestamp_header)
    current_time = int(time.time())
    return abs(current_time - delivery_time) <= tolerance_seconds
```

## Secret Rotation

When rotating your webhook secret, Taskmoor supports a transition period where both old and new secrets are valid:

1. Update the webhook with a new secret via the API:

```bash
curl -X PATCH https://api.taskmoor.com/v2/webhooks/wh_01HXYZ \
  -H "Authorization: Bearer tm_test_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{"secret": "whsec_new_signing_secret"}'
```

2. During the 1-hour transition window, Taskmoor sends two signature headers: `X-Taskmoor-Signature` (new secret) and `X-Taskmoor-Signature-Old` (previous secret).
3. Update your verification code to check both signatures during this window.
4. After the transition window closes, only the new signature is sent.

## Rejecting Invalid Requests

Your webhook endpoint should return:

| Scenario | HTTP Response | Action |
|----------|:------------:|--------|
| Valid signature | `200 OK` | Process the payload |
| Invalid signature | `401 Unauthorized` | Log the rejection; do not process |
| Missing signature header | `400 Bad Request` | Reject the request |
| Expired timestamp | `403 Forbidden` | Log as potential replay; do not process |

## Security Best Practices

- Always verify the HMAC signature before processing any webhook payload.
- Use constant-time comparison to prevent timing side-channel attacks.
- Store your webhook secret in a secrets manager, not in source code.
- Validate the `X-Taskmoor-Timestamp` header to reject stale or replayed deliveries.
- Serve your webhook endpoint over HTTPS only.
- Rotate webhook secrets at least every 180 days.
