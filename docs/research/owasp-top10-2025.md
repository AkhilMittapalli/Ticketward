# OWASP Top 10:2025 Mapping - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-27
**Last Updated**: 2026-09-27
**Status**: Open (stub; research not started)
**Owner phase**: P9 (ASVS L2 checklist pass; verify the §12.3 mapping)
**Category**: Security / Risk mapping
**Linked ADR(s)**: ADR-0027 (target OWASP ASVS L2; §12.3 remapped to Top 10:2025 in v1.1)
**Spec sections**: §12.3, §12.4 (the separate LLM Top 10), §16 P9, §23

---

## EXECUTIVE SUMMARY

- This is a **stub**. It was created for the spec v1.1 topic list (A-26), and no research has been run yet.
- It collects the required questions and points to findings that other research notes have already recorded. Nothing here is new, and nothing has been re-verified.
- Run the full protocol at P9. See [README.md](README.md) for the process and template.

---

## QUESTIONS (from spec §23)

1. What are the final OWASP Top 10:2025 categories, and when was it published?
2. Where does SSRF sit now?
3. How does every §12.3 control map to the new list?

---

## KNOWN SO FAR (recorded in other research notes; not re-verified)

- **Categories (Q1).** [owasp-asvs-l2.md](owasp-asvs-l2.md) F5 recorded that `https://top10.owasp.org/` redirected to the 2025 edition on 2026-09-26. It lists these categories:
  - A01 Broken Access Control
  - A02 Security Misconfiguration
  - A03 Software Supply Chain Failures
  - A04 Cryptographic Failures
  - A05 Injection
  - A06 Insecure Design
  - A07 Authentication Failures
  - A08 Software or Data Integrity Failures
  - A09 Security Logging and Alerting Failures
  - A10 Mishandling of Exceptional Conditions

  The page showed **no publication date**, and whether it is final was not established.
- **SSRF (Q2).** The same note records that the 2021 A10 (SSRF) is not a top-level 2025 category, and that **its 2025 placement is UNVERIFIED**. Its SI-S9 (remap §12.3 to the 2025 list) was applied in v1.1 via A-21, so this topic verifies the mapping.
- **SSRF-related controls already recorded (Q3 input):**
  - [owasp-asvs-l2.md](owasp-asvs-l2.md): ASVS 1.3.6 (SSRF allow-lists) and 13.2.4/13.2.5 (egress allow-lists).
  - [nextjs-security.md](nextjs-security.md): Next.js SSRF advisories CVE-2026-64649, CVE-2026-64645 and CVE-2026-44578, with their mitigations.
  - [auth-cookie-jwt-csrf.md](auth-cookie-jwt-csrf.md): PyJWT `PyJWKClient` SSRF, CVE-2026-48522.
- **Do not confuse the two lists.** [prompt-injection-defense.md](prompt-injection-defense.md) F1 records that the separate OWASP Top 10 for LLM Applications has a 2026 edition. That list is used in spec §12.4 (A-16), not in §12.3.
- **Not yet researched:** the publication date and final status, the placement of SSRF, and a control-by-control mapping of §12.3.

---

## FINDINGS

None yet. Research not started.

## DECISION / RECOMMENDATION

None yet.

## SPEC IMPACT

None yet.

## IMPLEMENTATION CHECKLIST

- [ ] At P9, read the Top 10:2025 category pages and release notes (primary source: owasp.org) and record the publication date and SSRF placement.
- [ ] Verify each §12.3 control row against the final categories, and update this file's status.

## OPEN RISKS / TO VERIFY

- The publication date and SSRF placement (UNVERIFIED in [owasp-asvs-l2.md](owasp-asvs-l2.md)).

## LINKED ADR

- **ADR-0027**: record the verified Top 10:2025 mapping alongside the ASVS evidence.

## SOURCES

Pointers only. Primary sources, with access dates, are listed in the linked notes: [owasp-asvs-l2.md](owasp-asvs-l2.md), [nextjs-security.md](nextjs-security.md), [auth-cookie-jwt-csrf.md](auth-cookie-jwt-csrf.md), [prompt-injection-defense.md](prompt-injection-defense.md).

---

**Document Version**: 0.1 (stub)
**Next Update**: P9
