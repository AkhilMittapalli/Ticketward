# ERPROT - Expert Research Protocol (Ticketward)

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Owner**: Akhil Mittapalli
**Governing spec**: the project spec v1.1: §0 (convention), §0.1 (research publishing), §23 (topics and required questions), DoD-11

---

## PURPOSE

This folder holds the project's **researched decisions**. Every architectural choice, model or library selection, unfamiliar technology, or bug with an unclear root cause gets an ERPROT document *before* implementation. The document:

- records the question;
- records what primary sources said (with access dates);
- records the recommendation and the concrete configuration to implement;
- names the risks still open;
- links the ADR that makes the decision binding.

These documents are **evidence, not the source of truth**. Precedence (spec v1.1): owner decisions > project brief > spec > ADRs > Wiki > code comments. When research contradicts the spec, the ERPROT file **does not edit the spec**. It records a **Spec impact** item, which is then applied through a spec change record, a version bump and ADR amendments. Spec v1.1 applied the first round.

DoD-11 requires an ERPROT document for every §23 topic, marked resolved.

### Publishing (owner decision D-04)

The research is published in the public repository as `docs/research/` by `scripts/sync_research.py`. The script refuses to publish, and writes nothing, if any doc contains:

- a local filesystem path (drive-letter user folders, `/Users/<name>/`, `/home/<name>/`, a OneDrive folder);
- a Markdown link that leaves this folder (targets starting with `../` or `/`), or any mention of the private knowledge-base folder path;
- a secret-like string (Anthropic, Hugging Face or GitHub tokens, AWS keys, Slack tokens, PEM private keys, or a fictional `tm_live_`/`tm_test_` key with a realistic body);
- a real e-mail address. Reserved domains (`example.com`/`.org`/`.net`, `.example`, `.test`, `.invalid`, `.localhost`) are allowed.

Rules for authors:

- Links between ERPROT docs and absolute `https://` links are fine.
- Refer to private documents in plain text, and prefer "the project spec §x" wording.
- Dry-run the scan with `scripts/sync_research.py --check` before committing. Only the lead publishes.

---

## THE PROCESS

| Step | Action | Output |
|---|---|---|
| 1. **PAUSE** | Stop before deciding or coding. Triggers: any architectural decision, model/library selection, unfamiliar tech, or a bug with an unclear root cause | - |
| 2. **DOCUMENT** | Write the question(s) in the session log (current-task.md): what must be decided, why, and by which phase | Question entry in the session log |
| 3. **RESEARCH** | Use **primary sources only**: official docs, standards (OWASP, IETF RFCs, NIST, W3C/WHATWG, MDN), vendor pricing pages, release notes, security advisories, papers, model cards. Record the **access date** for each. Use package registries (PyPI JSON, npm) and the GitHub Advisory Database for versions and CVEs | Notes + source list |
| 4. **DOCUMENT FINDINGS** | Write `<topic>.md` in this folder using the template below. Answer **every** §23 question for the topic. Anything unconfirmed is marked **UNVERIFIED — verify at build time**. Spec contradictions go under **SPEC IMPACT** | The ERPROT file |
| 5. **IMPLEMENT** | Implement the recommendation. Write or amend the linked ADR (MADR). Tests and configs cited in the file become ASVS / DoD evidence | Code + ADR |
| 6. **UPDATE** | Update the file's `Last Updated` and `Status`, and this index. Log the result in the session log and, where relevant, the system status, Wiki and implementation plan | Updated docs |

### Honesty rules (apply to every ERPROT file)

- **Never invent** versions, CVEs, prices, benchmark numbers or parameters. Where a value could not be confirmed from a primary source, write **UNVERIFIED — verify at build time**. Label estimates as estimates.
- Every factual claim cites a source with an **access date**. Prefer quoting identifiers (requirement IDs, CVE/GHSA IDs, config keys) and paraphrasing prose.
- Versions and prices go stale. Re-verify before the phase that uses them (spec R-14) and pin the exact versions in the ADR.
- Never edit the spec from an ERPROT file. Log a **Spec impact** row instead (location → finding → recommendation).
- A stub (status **Open**) may only point to findings already recorded in other ERPROT docs. It adds no new claims.

---

## DOCUMENT TEMPLATE

```markdown
# <Topic> - Expert Research Document

**Created**: YYYY-MM-DD
**Last Updated**: YYYY-MM-DD
**Status**: Resolved | Partially resolved (<what is still open>) | Open
**Owner phase**: Pn
**Category**: <e.g., Security / Authentication>
**Linked ADR(s)**: ADR-00xx (...)
**Spec sections**: §x.y, ...

---

## EXECUTIVE SUMMARY
<5-10 bullets: the answer, the recommendation, the headline risks, count of spec impacts>

## QUESTIONS
<numbered; must include every §23 question for this topic, plus derived questions>

## FINDINGS
### F1. <finding> (source, accessed YYYY-MM-DD)
<facts only, each with a source; tables for versions/prices/requirements>

## DECISION / RECOMMENDATION
### D1. <decision>
<concrete configs, code snippets, parameters, commands>

## SPEC IMPACT
| # | Spec location | Finding | Recommendation |

## IMPLEMENTATION CHECKLIST
- [ ] <phase-tagged tasks, including tests that serve as evidence>

## OPEN RISKS / TO VERIFY
<UNVERIFIED items, assumptions, things to re-check at build>

## LINKED ADR
<ADR(s) to create/amend and what they must record>

## SOURCES (all accessed YYYY-MM-DD)
<links>

---
**Document Version**: x.y
**Next Update**: <trigger or phase>
```

A stub keeps the same headings and adds a **KNOWN SO FAR** section after QUESTIONS. That section holds pointers to findings in other ERPROT docs.

### Status legend

| Status | Meaning |
|---|---|
| **Resolved** | All required questions are answered from primary sources, and the recommendation is ready to implement. Remaining items are routine "verify at build" pins |
| **Partially resolved** | Research is done, but an owner decision, a measurement or an availability check is pending. The file names exactly what is open |
| **Open** | Research not started (stub) or not yet sufficient to recommend |

---

## INDEX (all 26 topics from spec v1.1 §23)

- **Status** is read from each doc's header on 2026-09-27; the doc itself is authoritative.
- **Spec impact** gives the disposition in the spec v1.1 Changelog, with the change-record entry that applied it.
- Linked ADRs use the v1.1 numbering (spec §22), and owner phases follow spec §16.

| # | File | Category | Linked ADR(s) | Owner phase | Status | Spec impact |
|---|---|---|---|---|---|---|
| 1 | [`slm-model-selection.md`](slm-model-selection.md) | ML / base-model selection | ADR-0011 | P2 | Partially resolved: zero-shot bake-off and dev-laptop CPU tokens/s pending (P2) | Applied in spec v1.1 (A-02) |
| 2 | [`qlora-training-on-t4.md`](qlora-training-on-t4.md) | ML / fine-tuning | ADR-0012, ADR-0013 | P3 | Partially resolved: T4 smoke test per finalist; Kaggle quota numbers | Applied in spec v1.1 (A-03) |
| 3 | [`synthetic-data-generation.md`](synthetic-data-generation.md) | Data / generation | ADR-0016, ADR-0031 | P1 | Partially resolved: 50-record pilot per generator family | Applied in spec v1.1 (A-01, A-11) |
| 4 | [`leakage-and-dedup.md`](leakage-and-dedup.md) | Data / evaluation integrity | ADR-0016 | P1 | Partially resolved: τ_emb calibration on the P1 data | Applied in spec v1.1 (A-12) |
| 5 | [`bitext-ood-dataset.md`](bitext-ood-dataset.md) | Data / OOD evaluation | ADR-0016 | P1 | Resolved | Applied in spec v1.1 (A-13) |
| 6 | [`confidence-calibration.md`](confidence-calibration.md) | ML / confidence and gating | ADR-0017 | P3-P4 (τ re-fit P6) | Partially resolved: threshold values need P3 outputs | Applied in spec v1.1 (A-04) |
| 7 | [`constrained-decoding.md`](constrained-decoding.md) | ML serving / schema validity | ADR-0014, ADR-0017 | P2-P4 | Partially resolved: measured accuracy/latency effect (P2) | Applied in spec v1.1 (ADR-0014 amendment) |
| 8 | [`gguf-export-and-ollama.md`](gguf-export-and-ollama.md) | ML serving / packaging | ADR-0014 | P3 | Partially resolved: end-to-end conversion, drift and template-parity tests (P3) | Applied in spec v1.1 (ADR-0014 amendment) |
| 9 | [`hybrid-retrieval.md`](hybrid-retrieval.md) | Retrieval | ADR-0005, ADR-0007, ADR-0009 | P5 | Partially resolved: CPU reranker latency and ablations (P5) | Applied in spec v1.1 (A-14) |
| 10 | [`embedding-model-choice.md`](embedding-model-choice.md) | Retrieval / embeddings | ADR-0008 | P5 | Partially resolved: bake-off on the P5 qrels | Applied in spec v1.1 (A-14, A-12) |
| 11 | [`citation-verification.md`](citation-verification.md) | Retrieval / grounding | ADR-0033, ADR-0009 | P6 | Partially resolved: calibration set (P6) and CPU latency | Applied in spec v1.1 (A-15) |
| 12 | [`prompt-injection-defense.md`](prompt-injection-defense.md) | Security / LLM | ADR-0034, ADR-0010 | P6 | Partially resolved: the header still lists the license decision, since taken (D-05); corpus evaluation pending | Applied in spec v1.1 (A-16, D-05) |
| 13 | [`pii-masking-presidio.md`](pii-masking-presidio.md) | Security / privacy | ADR-0019, ADR-0030 | P4 | Partially resolved: spaCy md-vs-lg latency and the 200-ticket fixture (P4) | Applied in spec v1.1 (A-17) |
| 14 | [`frontier-provider-anthropic.md`](frontier-provider-anthropic.md) | Providers / frontier LLM | ADR-0015 | P7 | Resolved for research: owner vendor-review sign-off and retention confirmation pending | Applied in spec v1.1 (A-18, A-01) |
| 15 | [`auth-cookie-jwt-csrf.md`](auth-cookie-jwt-csrf.md) | Security / authentication and sessions | ADR-0020, ADR-0021, ADR-0040 | P4 | Resolved: open decisions taken (D-01, A-20) | **Partly deferred**: SI-A6 (MFA) deferred by D-01; the rest applied (A-20) |
| 16 | [`owasp-asvs-l2.md`](owasp-asvs-l2.md) | Security / compliance baseline | ADR-0027, ADR-0040 | P9 (checklist seeded at P0) | Resolved | **Partly deferred**: SI-S2 (MFA) follows D-01; the rest applied (A-21) |
| 17 | [`observability-otel.md`](observability-otel.md) | Operations / observability | ADR-0024, ADR-0022 | P7 | Resolved | Applied in spec v1.1 (A-22) |
| 18 | [`vllm-production-serving.md`](vllm-production-serving.md) | ML serving / production path | ADR-0014 | P10 (analysis; stretch G-2) | Partially resolved: throughput and cost are analytical only (G-2) | Applied in spec v1.1 (A-19) |
| 19 | [`public-demo-deployment.md`](public-demo-deployment.md) | Deployment / operations | ADR-0026, ADR-0035 | P9 (host decision) / P11 (deploy) | Partially resolved: host at P9 (D-06); Cloudflare phase; domain | Applied in spec v1.1 (A-23; host choice scheduled by D-06) |
| 20 | [`evaluation-statistics.md`](evaluation-statistics.md) | Evaluation / statistics | ADR-0032, ADR-0016 | P2, P10 | Resolved: `evals/ANALYSIS_PLAN.md` due before P10 | Applied in spec v1.1 (A-10) |
| 21 | [`nextjs-security.md`](nextjs-security.md) | Security / frontend | ADR-0023 | P8 | Resolved | Applied in spec v1.1 (A-24) |
| 22 | [`encoder-baseline.md`](encoder-baseline.md) | ML / baselines | ADR-0018 | P2 | **Open** (stub) | None yet (topic added by A-26) |
| 23 | [`job-queue-arq.md`](job-queue-arq.md) | Backend / async jobs | ADR-0022 | P4 (P7 tracing, P9 Redis ACL/TLS) | **Open** (stub) | None yet (topic added by A-26) |
| 24 | [`cryptography-key-management.md`](cryptography-key-management.md) | Security / cryptography | ADR-0030, ADR-0037, ADR-0020 | P4 (P9 SOPS + age, restore drill) | **Open** (stub) | None yet (topic added by A-26) |
| 25 | [`owasp-top10-2025.md`](owasp-top10-2025.md) | Security / risk mapping | ADR-0027 | P9 | **Open** (stub) | None yet (topic added by A-26) |
| 26 | [`python-packaging.md`](python-packaging.md) | Engineering / packaging and base images | ADR-0002, ADR-0003 | P9 (base images); P0 items to verify | **Open** (stub) | None yet (topic added by A-26) |

---

## DECISIONS THAT CLOSED OPEN RESEARCH ITEMS (spec v1.1, 2026-09-26)

These come from the v1.1 change record: owner decisions D-xx and lead adjudications A-xx. Each closed an item that a research doc had left open.

| Decision | What was decided | Closes |
|---|---|---|
| **D-05** (owner) | Prompt-injection detector = **Llama Prompt Guard 2 22M**. The owner accepts the gated Llama 4 Community License; pinned revision, safetensors only, no remote code; "Built with Llama" attribution; CI uses recorded detector outputs; the policy engine stays the primary control (ADR-0034) | The detector/license decision in [`prompt-injection-defense.md`](prompt-injection-defense.md). The corpus evaluation is still pending |
| **A-01** (adjudication) | Generator families: Family A `openai/gpt-oss-120b` (train/val), Family B `mistralai/Mistral-Large-3-675B-Instruct-2512` (test_synth). **Never train on Claude outputs**, enforced by a CI provenance check; budget $15 (ADR-0031) | The generator choice in [`synthetic-data-generation.md`](synthetic-data-generation.md); the Claude-training restriction noted in [`frontier-provider-anthropic.md`](frontier-provider-anthropic.md). The 50-record pilot is still pending |
| **D-06** (owner) | The public demo host is **decided at P9, after the CPU latency benchmark** on the real stack. The options and dated costs stay listed (ADR-0026) | Schedules the host-SKU decision in [`public-demo-deployment.md`](public-demo-deployment.md). The Cloudflare phase and the domain remain open |
| **D-01** (owner) | **MFA deferred** to after v1.0, with a documented ASVS L2 exception and compensating controls (ADR-0040) | The MFA scope in [`auth-cookie-jwt-csrf.md`](auth-cookie-jwt-csrf.md) (SI-A6) and [`owasp-asvs-l2.md`](owasp-asvs-l2.md) (SI-S2) |
| **A-20** (adjudication) | Sessions 24 h absolute / 60 min idle (4 h in demo mode); refresh cookie `__Secure-tw_refresh` with a documented ASVS 3.3.3 deviation | The session-lifetime and refresh-cookie decisions in [`auth-cookie-jwt-csrf.md`](auth-cookie-jwt-csrf.md) |
| **D-04** (owner) | ERPROT published publicly as `docs/research/` through the sync script (ADR-0038) | Publication of this folder |

---

## MAINTENANCE

- When a topic is revisited, bump `Document Version`, update `Last Updated`, and keep superseded findings in a short "Change log" line rather than deleting them.
- Re-verify versions and prices at the start of the phase that consumes them (spec R-14), and whenever a security advisory lands for a pinned dependency.
- Keep this index in sync: add a row when §23 gains a topic, and update the Status and Spec impact columns when a doc's header or the spec changes.
- Run `scripts/sync_research.py --check` after every edit. It must report no private-content findings.

---

**Change log**: 2026-09-27: index extended to 26 topics (spec v1.1 §23, A-26); statuses read from doc headers; Spec impact column and closing decisions added; publishing rules (D-04) added.

**Document Version**: 1.1
**Next Update**: When any doc's status changes, or when §23 gains a topic
