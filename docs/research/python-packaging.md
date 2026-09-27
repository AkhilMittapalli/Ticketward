# Python Packaging, Toolchain and Base Images - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-27
**Last Updated**: 2026-09-27
**Status**: Open (stub; research not started)
**Owner phase**: P9 for the base images (A-29). The P0 items (uv pin, two projects, Python ranges) were built by the scaffold and still need verification here.
**Category**: Engineering / Packaging and containers
**Linked ADR(s)**: ADR-0002 (Python pin; ml allows 3.12–3.13), ADR-0003 (uv; two independent projects; uv 0.9.6; `--locked`/`--frozen`)
**Spec sections**: §12.9 (container hardening, base images), §14.2, §16 P0/P9, §23

---

## EXECUTIVE SUMMARY

- This is a **stub**. It was created for the spec v1.1 topic list (A-26), and no research has been run yet.
- It collects the required questions and points to findings that other research notes have already recorded. Nothing here is new, and nothing has been re-verified.
- The base-image question (`python:3.12-slim-trixie` vs bookworm vs distroless, digest pinning) must be researched before the P9 Dockerfile work. See [README.md](README.md) for the process and template.

---

## QUESTIONS (from spec §23)

1. How is uv pinned, and what is the upgrade policy (0.9.6; `--locked` vs `--frozen`)?
2. Two independent projects, or a workspace?
3. Which Python ranges (backend 3.12; ml 3.12–3.13)?
4. How do we use the platform's torch on Kaggle/Colab?
5. Which wheels are available (bitsandbytes, causal-conv1d, spaCy models by URL + sha256)?
6. **Base images (P9, A-29):** `python:3.12-slim-trixie`, bookworm (oldstable) or distroless? How do we pin digests?

---

## KNOWN SO FAR (recorded in other research notes; not re-verified)

- **Python ranges and platform torch (Q3, Q4).** [qlora-training-on-t4.md](qlora-training-on-t4.md) recorded:
  - The Colab GPU runtime runs Python 3.13 with torch 2.11.0+cu130.
  - The Kaggle GPU image runs Python 3.12 with torch 2.11 (verify there with `python -V`).
  - The ml project therefore needs `requires-python >=3.12,<3.14`, must **not** lock torch (its SI-5, applied in v1.1 via A-03), and pins `huggingface-hub<2` (SI-8).
- **Wheels (Q5).** The same note records:
  - bitsandbytes 0.50.2 supports Turing (sm_75) and ships CUDA 13 wheels.
  - Two items are **UNVERIFIED**: causal-conv1d 1.7.0 / flash-linear-attention 0.5.2 support for sm_75, and Python 3.13 wheels for bitsandbytes and causal-conv1d.
  - The current Unsloth wheel pins conflict with TRL 1.x.
- **spaCy models (Q5).** [pii-masking-presidio.md](pii-masking-presidio.md) recommends installing `en_core_web_md-3.8.0` from the spaCy models GitHub release **by URL plus sha256** in `uv.lock`, and pinning presidio 2.2.364 and spaCy 3.8.x.
- **Base-image signals (Q6).** [hybrid-retrieval.md](hybrid-retrieval.md) records that the pgvector 0.8.6 images come in both bookworm (`0.8.6-pg16`) and trixie (`0.8.6-pg16-trixie`) variants.
- **Serving runtime (Q3 context).** [vllm-production-serving.md](vllm-production-serving.md) records that vLLM 0.30.0 supports Python 3.10–3.13 on Linux only.
- **Not yet researched:** the uv release cadence and upgrade policy, the `--locked` vs `--frozen` semantics, the workspace trade-offs, a base-image comparison (security updates, size, glibc, CVE counts) and the digest-pinning workflow.

---

## FINDINGS

None yet. Research not started.

## DECISION / RECOMMENDATION

None yet. Spec v1.1 currently names `python:3.12-slim-trixie` pinned by digest (A-29), uv 0.9.6 (ADR-0003) and two independent uv projects. This topic verifies or amends them.

## SPEC IMPACT

None yet.

## IMPLEMENTATION CHECKLIST

- [ ] Verify the P0 toolchain choices (uv pin, `--locked`/`--frozen` usage, Python ranges) from primary sources (uv docs and release notes, python.org, Debian release pages, the Docker Official Images docs), with access dates.
- [ ] Before the P9 Dockerfile work, compare the trixie, bookworm and distroless bases; record the chosen tags and digests, and update this file's status.

## OPEN RISKS / TO VERIFY

- Wheel availability on Python 3.13 and sm_75 kernels (UNVERIFIED in [qlora-training-on-t4.md](qlora-training-on-t4.md)).

## LINKED ADR

- **ADR-0002** and **ADR-0003**: confirm the toolchain pins and the base-image choice (with digests).

## SOURCES

Pointers only. Primary sources, with access dates, are listed in the linked notes: [qlora-training-on-t4.md](qlora-training-on-t4.md), [pii-masking-presidio.md](pii-masking-presidio.md), [hybrid-retrieval.md](hybrid-retrieval.md), [vllm-production-serving.md](vllm-production-serving.md).

---

**Document Version**: 0.1 (stub)
**Next Update**: Before the P9 Dockerfile work (base images); P0 items at the next toolchain upgrade
