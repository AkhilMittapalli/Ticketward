# Cryptography and Key Management - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-27
**Last Updated**: 2026-09-27
**Status**: Open (stub; research not started)
**Owner phase**: P4 (period DEKs in `core/crypto.py`, key tables, auth key rings). SOPS + age and the restore drill with deletion-ledger re-apply are P9.
**Category**: Security / Cryptography and key management
**Linked ADR(s)**: ADR-0030 (app-level AES-GCM + retention/crypto-shred), ADR-0037 (per-period DEKs wrapped by a KEK; deletion ledger), ADR-0020 (ES256 key rings, CSRF HMAC keys); related ADR-0027 (ASVS V11 evidence)
**Spec sections**: §10, §12.6, §16 P4/P9, §23

---

## EXECUTIVE SUMMARY

- This is a **stub**. It was created for the spec v1.1 topic list (A-26), and no research has been run yet.
- It collects the required questions and points to findings that other research notes have already recorded. Nothing here is new, and nothing has been re-verified.
- Run the full protocol before P4 implements `core/crypto.py`. See [README.md](README.md) for the process and template.

---

## QUESTIONS (from spec §23)

1. How is the AES-256-GCM envelope designed (nonces, AAD)?
2. How are per-period DEKs wrapped by a KEK, and how are they rotated and destroyed?
3. Where does the KEK live (SOPS + age, Docker secrets)?
4. How is the deletion ledger re-applied after a restore?
5. How are the ES256 key rings and the CSRF HMAC keys handled?
6. What goes into the crypto inventory for ASVS V11?

---

## KNOWN SO FAR (recorded in other research notes; not re-verified)

- **Envelope (Q1).** [pii-masking-presidio.md](pii-masking-presidio.md) designs the PII-map envelope:
  - AES-256-GCM with a 96-bit nonce, and AAD that binds `ticket_id`, purpose and `key_id`.
  - `(key_id, nonce, ciphertext)` is stored with the ticket and crypto-shredded through the retention job.
  - Its SI-4 (`pii_map_enc`, `pii_map_key_id`) was applied in v1.1 via A-17.
- **Key rings (Q5).** [auth-cookie-jwt-csrf.md](auth-cookie-jwt-csrf.md) D3/D7/D10 record:
  - The ES256 signing key is a Docker-secret PEM, with the previous public key kept as verify-only.
  - `kid` is the RFC 7638 thumbprint, computed at startup.
  - A rotation runbook drops the previous key after the access-token TTL plus leeway and deploy skew.
  - CSRF HMAC keys are held as `[current, previous]`.
  - Service tokens use a separate ES256 key ring.
  - F7 there covers RFC 9864 and the PyJWT advisories.
- **ASVS V11 (Q6).** [owasp-asvs-l2.md](owasp-asvs-l2.md) F4/D2/D4 record:
  - The L2 requirements: 11.1.1 (a key-management policy following NIST SP 800-57), 11.1.2 (crypto inventory), 11.2.2 (crypto agility), 11.3.2/11.3.3 (approved authenticated encryption) and 11.5.1 (CSPRNG values of at least 128 bits; the standard notes that UUIDs do not qualify).
  - A first inventory list: JWT ES256 keys, CSRF HMAC keys, AES-GCM row keys, TLS and restic.
  - SOPS + age as the recommendation for 13.3.1 (secrets manager).
- **KEK and secrets storage (Q3).** [public-demo-deployment.md](public-demo-deployment.md) D9/D10 record:
  - SOPS + age-encrypted secrets are decrypted on the host into `/run/secrets` (mode 0400).
  - restic encrypts repository data client-side; its cipher details are marked UNVERIFIED there.
  - The restic password must be kept off the VM.
- **Random values.** [nextjs-security.md](nextjs-security.md) D2 generates CSP nonces from 16 random bytes rather than `crypto.randomUUID()`, per ASVS 11.5.1.
- **Not yet researched:** DEK period length and rotation, KEK storage and access mechanics, destruction evidence, and the deletion-ledger re-apply procedure after a restore.

---

## FINDINGS

None yet. Research not started.

## DECISION / RECOMMENDATION

None yet. ADR-0037 currently fixes per-period DEKs wrapped by a KEK, a deletion ledger re-applied after restores, and backups that hold only wrapped keys.

## SPEC IMPACT

None yet.

## IMPLEMENTATION CHECKLIST

- [ ] Run ERPROT research for Q1–Q6 before P4, from primary sources (NIST SP 800-38D and SP 800-57, `cryptography` library docs, SOPS/age docs), with access dates.
- [ ] Produce the crypto inventory structure for `docs/security/crypto-inventory.md` (ASVS 11.1.2), and update this file's status.

## OPEN RISKS / TO VERIFY

- restic cipher details (UNVERIFIED in [public-demo-deployment.md](public-demo-deployment.md)).
- The exact AAD fields and nonce strategy for the ticket-text envelope, which so far are designed only for the PII map.

## LINKED ADR

- **ADR-0030** and **ADR-0037**: record the envelope format, DEK period, KEK location, rotation, destruction and ledger procedure.
- **ADR-0020**: key-ring rotation.

## SOURCES

Pointers only. Primary sources, with access dates, are listed in the linked notes: [pii-masking-presidio.md](pii-masking-presidio.md), [auth-cookie-jwt-csrf.md](auth-cookie-jwt-csrf.md), [owasp-asvs-l2.md](owasp-asvs-l2.md), [public-demo-deployment.md](public-demo-deployment.md), [nextjs-security.md](nextjs-security.md).

---

**Document Version**: 0.1 (stub)
**Next Update**: Before P4 implements `core/crypto.py`
