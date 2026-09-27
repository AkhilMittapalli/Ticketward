# Leakage Detection and Deduplication - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Partially resolved (methods, parameters, handling policy and code resolved; the numeric embedding threshold τ_emb must be calibrated on the real P1 data using the protocol in D5)
**Category**: ML Data / Evaluation integrity
**Linked ADR(s)**: ADR-0016 (test set from a different family + hard set + Bitext OOD), amend with the leakage method; ADR-new "Evaluation statistics protocol" (see evaluation-statistics.md) for the hard-set dev/final split
**Spec sections**: §9.3 (leakage checks), §9.1.8 (provenance), §8.1/§8.9 (KB, retrieval eval), §16 (v0.2 iteration), §19 DoD-6, §20 L-06, §21 R-01, §23

---

## EXECUTIVE SUMMARY

1. **Six checks.** Each is applied to named split pairs (D2):
   - exact SHA-256 of normalized text;
   - lexical near-duplicates (MinHash-LSH candidates, then exact Jaccard);
   - embedding near-duplicates (bge-small-en-v1.5 cosine);
   - template, scenario and pool disjointness;
   - KB-passage copying (≥ 30 consecutive word tokens);
   - protected-string copying (spec examples, demo tickets, prompt and guideline text).
2. **Key finding: the spec's MinHash setting misses most borderline pairs.** Taken literally, it is `MinHashLSH(threshold=0.7, num_perm=128)` with datasketch's default weights.
   - datasketch picks bands and rows by minimizing *equally weighted* false-positive and false-negative areas. That yields **b=14, r=9**.
   - A pair with true Jaccard 0.70 then becomes a candidate with probability **0.44**; at 0.80 the probability is 0.87.
   - A leakage audit needs recall. Use LSH only to generate candidates: `threshold=0.5, weights=(0.2, 0.8)` gives b=30, r=4, and **P(candidate | J=0.70) = 0.9997**. Then **verify with exact Jaccard ≥ 0.70**.
   - At our scale (about 4,050 train+val × 1,320 protected items), exact all-pairs Jaccard through a sparse matrix product takes seconds. It is the CI source of truth; LSH is the scalable path.
3. **Shingle unit.** The spec's "5-gram shingles" does not say whether the unit is characters or words. Tickets are short (the terse bucket is 5–40 words), and a single word change alters up to five word-5-grams. The recommendation is **character 5-grams over normalized text**, with word 5-grams reported as a secondary signal. Planted-duplicate calibration confirms the choice.
4. **Embedding threshold.** The bge-small-en-v1.5 model card says to pick a similarity threshold from *your own data's* score distribution. The spec's 0.92 is therefore only a starting value. D5 gives a calibration protocol:
   - planted near-duplicates of several types;
   - same-intent, same-product-area hard negatives;
   - human-labeled natural nearest-neighbor pairs.
   The decision rule chooses the **lowest τ** that keeps the hard-negative flag rate ≤ 1% and train removals ≤ 5%. The rationale is asymmetric cost: a false positive only drops a train record; a false negative inflates test metrics.
5. **Handling policy.**
   - A cross-split flag drops the **train/val member**, never the test member (spec).
   - Two situations the spec leaves open are handled by **replacing the test item before freeze**, regenerated from the same stratum: duplicates *within* a test split, and test tickets that copy KB text.
   - After the P1 freeze, test splits are immutable. Any change is a new version with full re-evaluation.
6. **v0.2 risk.** New train data written from hard-set error analysis (§16) can leak the hard set's content without tripping thresholds. Mitigations: stricter thresholds for that batch, an owner attestation, and the hard-set dev/final split recommended in evaluation-statistics.md.

---

## QUESTIONS

| # | Question | Source |
|---|---|---|
| Q1 | What MinHash parameters (shingle unit and size, permutations, LSH threshold, bands and rows)? | §23 |
| Q2 | How is the embedding near-duplicate threshold selected? | §23 |
| Q3 | How is template leakage prevented and detected? | §23 |
| Q4 | How is KB-text overlap detected, and on which text? | §9.3 |
| Q5 | How are flagged pairs handled (train vs test, before and after freeze)? | §23 |
| Q6 | (Implementer) Which split pairs are checked, what does the report look like, and what is the CI gate? | §9.3 |
| Q7 | (Implementer) Code sketch. | – |

---

## FINDINGS

All sources accessed 2026-09-26.

### F1. datasketch API and the LSH parameter optimizer (Q1)

- **PyPI state:** datasketch **2.0.0**, MIT, Python ≥ 3.9 [L3]. Version 2.0.0 changed the default MinHash permutation scheme to `"affine32"`. The package notes say this fixes a similarity over-estimation bias on large sets, halves sketch memory and speeds up updates. The `"legacy"` (pre-2.0) and `"affine64"` schemes remain, and **signatures from different schemes cannot be compared or merged** [L2]. Pin the version, and never mix persisted 1.x signatures with 2.x ones.
- **`MinHash`** takes `num_perm=128` and `seed=1`, with `hashfunc`, `hashvalues`, `permutations` and `scheme` options. It provides `update_batch`, `jaccard`, and the class methods `bulk` and `generator` [L2]. The master branch also shows a `gpu_mode` argument; whether 2.0.0 ships it is UNVERIFIED, so do not use it.
- **`MinHashLSH`** defaults: `threshold=0.9`, `num_perm=128`, `weights=(0.5, 0.5)`, `params=None` [L1]. With `params=None` it picks `(b, r)` with `b·r ≤ num_perm` to minimize `w_fp·FP + w_fn·FN`, where:
  - FP = ∫₀ᵗ [1 − (1 − s^r)^b] ds
  - FN = ∫ₜ¹ [1 − (1 − (1 − s^r)^b)] ds
  - The weights must sum to 1.

### F2. Computed S-curves (reimplementation of datasketch's optimizer, this session)

P(candidate | true Jaccard s) = 1 − (1 − s^r)^b:

| num_perm | LSH threshold | weights (fp, fn) | chosen b × r | s=0.50 | s=0.60 | s=0.65 | **s=0.70** | s=0.80 |
|---|---|---|---|---|---|---|---|---|
| 128 | 0.7 | (0.5, 0.5), the default | 14 × 9 | 0.027 | 0.132 | 0.254 | **0.438** | 0.867 |
| 128 | 0.7 | (0.2, 0.8) | 18 × 7 | 0.132 | 0.400 | 0.595 | **0.787** | 0.986 |
| 128 | 0.7 | (0.1, 0.9) | 20 × 6 | 0.270 | 0.615 | 0.792 | **0.918** | 0.998 |
| 128 | 0.6 | (0.2, 0.8) | 23 × 5 | 0.518 | 0.845 | 0.941 | **0.985** | 1.000 |
| **128** | **0.5** | **(0.2, 0.8)** | **30 × 4** | 0.856 | 0.985 | 0.997 | **0.9997** | 1.000 |
| 256 | 0.7 | (0.5, 0.5) | 25 × 10 | 0.024 | 0.141 | 0.287 | 0.511 | 0.942 |

- **Estimator noise.** The MinHash estimate of J has standard error ≈ √(J(1−J)/k). At k=128 that is 0.040 for J=0.7, and 0.029 at k=256. **Never threshold the estimate itself; verify candidates with exact Jaccard.**
- **Web-scale reference point.** Hugging Face datatrove's `MinhashConfig` defaults to 5-grams with 14 buckets × 8 hashes (112 hashes). Its comments give the target threshold as (1/14)^(1/8) ≈ 0.72 and the inclusion probability at s=0.8 as 0.924 [L4]. That is web-scale dedup tuned for throughput; our audit needs recall.
- **Why the checks matter.** Lee et al. (ACL 2022) found many near-duplicates in standard corpora, and train–test overlap affecting over 4% of the validation set of standard benchmarks. Their NearDup and ExactSubstr tools reduced memorization about tenfold [L5]. Near-duplicate leakage measurably inflates evaluation.

### F3. Shingle unit for short tickets (Q1): analysis

- A 30-word terse ticket has 26 word-5-grams. Substituting one word changes up to 5 of them, so two near-identical terse tickets can fall below J=0.7 on word shingles.
- Character 5-grams over normalized text degrade gracefully under word substitutions, typos and inflection. The trade-off is a higher baseline similarity between same-topic tickets, which the hard-negative calibration (D5) controls.
- Normalization should neutralize the parts of the text that templates change most:
  - digits → `0` (amounts, ids, dates);
  - typed PII placeholders (`<EMAIL_1>` → `<email>`);
  - case and whitespace.
- **Decision:** char-5 Jaccard is the gate; word-5 Jaccard is reported only. This is analysis, not a literature value; D5 confirms it on data.

### F4. Embedding similarity with bge-small-en-v1.5 (Q2)

The model card [L6] gives:
- 384-d embeddings, a 512-token max sequence, MIT license.
- `normalize_embeddings=True` is recommended for cosine.
- v1.5 has a more reasonable similarity distribution than v1 (v1 scores clustered in about [0.6, 1]).
- For similarity filtering, choose the threshold from the similarity distribution of *your* data (the card mentions values such as 0.8, 0.85 or 0.9), because relative order matters more than absolute scores.
- The query instruction is for retrieval; symmetric similarity does not need it.

Two consequences:
- **0.92 must be calibrated, not assumed.**
- Tickets longer than 512 tokens are truncated for embedding. Near-duplicate detection on long tickets then relies on the lexical check.

sentence-transformers is at **6.1.0** on PyPI (Apache-2.0, Python ≥ 3.10) [L7]. The v6 `encode` signature was not fully visible in the docs fetched this session, so the code sketch normalizes vectors with NumPy rather than relying on a keyword argument.

### F5. Template leakage and shortcut cues (Q3)

- Data-construction artifacts let models reach high accuracy from superficial cues. The hypothesis-only NLI baselines are the classic example (Gururangan et al., NAACL 2018) [L8].
- For us, "template leakage" has three forms:
  1. **Structural sharing.** Train and test come from the same prompt template, few-shot exemplars, persona or company pool, or scenario seed.
  2. **Label-correlated generator cues.** Subject lines restate the label; intent keywords appear in every ticket.
  3. **Echo of prompt text.** Fact-sheet or instruction phrases get copied into tickets.
- Structural sharing is **prevented by construction**: families, templates and pools are disjoint per split (synthetic-data-generation.md, D3), and CI **asserts** it. The cue forms are **detected by probes**, because they are not duplicates at all.

### F6. KB overlap (Q4): rationale

- Retrieval is evaluated on queries built from test tickets (§8.9 qrels). A ticket that copies ≥ 30 consecutive tokens of a KB passage makes BM25 retrieval and citation support artificially easy, which inflates M-05 and M-06.
- Only **customer-authored** text should be checked: subject, message, and prior messages with `author=customer`. Synthetic agent replies in a thread may legitimately quote `reply_template` documents; those are reported separately.

### F7. Scale (Q6)

| Comparison | Pairs |
|---|---|
| train (3,600) + val (450) vs protected: test_synth 720 + test_hard 100 + test_ood 500 = 1,320 | ≈ 5.35M |
| Within train | ≈ 8.2M unordered pairs |

- Exact sparse Jaccard over the cross-split pairs and a 4,050 × 1,320 cosine matrix both finish in seconds on the dev laptop.
- Within-train exact Jaccard should be chunked or use the LSH path.

---

## DECISION / RECOMMENDATION

### D1. Text normalization (shared by all checks)

- **Text compared:** `customer_text` = subject + "\n" + message + "\n" + the bodies of prior messages whose `author == "customer"`.
- **Normalization:** NFKC → typed placeholders `<EMAIL_1>` → `<email>` → lowercase → every digit run → `0` → collapse whitespace → strip. Placeholders are rewritten *before* lowercasing because the placeholder regex is uppercase; getting this order wrong was a bug caught in testing.
- **Stable hashes:** `sha256(normalized)` for exact matches; `blake2b(digest_size=8)` for n-gram sets. Do not use Python `hash()`: it is salted per process, which breaks reproducibility.

### D2. Checks, pairs, thresholds, actions

"Trainable" = {train, val}. "Protected" = {test_synth, test_hard, test_ood, e2e_scenarios}.

| ID | Check | Split pairs | Flag rule | Action |
|---|---|---|---|---|
| C1 | Exact duplicate (normalized SHA-256) | all cross-split pairs; within each split | equal hash | Trainable × protected: drop the trainable record. Within train: keep the first `record_id`. Within protected or test_synth × test_hard: replace before freeze |
| C2 | Lexical near-duplicate | trainable × protected; train × val; within each protected split; test_synth × test_hard | exact char-5 Jaccard ≥ **0.70** (candidates from LSH t=0.5, w=(0.2,0.8), 128 perms, or the exact sparse path). Report-only band 0.50–0.70 | As C1. train × val: drop the train record |
| C3 | Embedding near-duplicate | same as C2 | cosine ≥ **τ_emb** (start 0.92, calibrated per D5) | As C1 |
| C4 | Structural disjointness | trainable vs protected (all ids); train vs val (`template_id`, `scenario_seed`) | any shared `template_id`, `scenario_seed`, `persona_id`, `company_id`, invoice-id prefix | **CI failure.** Fix the generator (must be zero by construction) |
| C5 | KB copying | customer_text of every split vs all KB versions (approved, draft, adversarial, retired) | any shared 30-token window (word tokens after D1). Report-only: longest run ≥ 12 | Protected: replace before freeze (CI fails until done). Trainable: drop or regenerate |
| C6 | Protected strings | trainable and test_synth vs spec §5.1 examples, §17 demo tickets, `docs/labeling_guidelines.md` examples, generator prompt and fact-sheet text | char-5 Jaccard ≥ 0.60 against any protected sentence, or containment of an ≥ 8-word span | Trainable: drop. test_synth: replace before freeze. Generator prompts must never contain these strings |
| C7 | Within-train near-duplicate (quality, not leakage) | within train, within val | exact char-5 Jaccard ≥ 0.80 | Keep the first; drop the rest; refill the quota |

The thresholds in C2, C3, C6 and C7 are **initial values**; D5 confirms or adjusts them. The chosen values and the calibration report id are written into every leakage report.

### D3. MinHash configuration (Q1)

- **Shingles:** character 5-grams of the D1-normalized `customer_text`. Word 5-grams (`[a-z0-9]+` tokens) are computed too and reported.
- **Sketch:** `MinHash(num_perm=128, seed=1)` (datasketch 2.0.0 default scheme `affine32`; pin it).
- **Candidates:** `MinHashLSH(threshold=0.5, num_perm=128, weights=(0.2, 0.8))`. Assert `(lsh.b, lsh.r) == (30, 4)`; if a datasketch upgrade changes the optimizer, CI catches it. Explicit `params=(32, 4)` is an equivalent choice.
- **Verification:** exact Jaccard on the shingle sets for every candidate. Flag if ≥ 0.70.
- **CI truth path:** exact all-pairs Jaccard via a sparse product whenever |trainable| × |protected| ≤ 50M pairs (true here). LSH is used for within-train C7 and for any future larger corpora.

### D4. Embedding configuration

- **Model:** `BAAI/bge-small-en-v1.5` at a pinned HF revision, on CPU, **without** the query instruction (symmetric task).
- **Input:** `customer_text` truncated by the model at 512 tokens. Embeddings are L2-normalized in NumPy.
- **Scoring:** cross-split cosine `S = E_protected @ E_trainable.T`.
- **Diagnostics:** nearest-neighbor similarity histograms for trainable → trainable (excluding self), test_synth → train, test_hard → train and test_ood → train are written into the report. If more than 5% of a protected split is flagged at τ_emb, the threshold is catching *topic* similarity, not leakage; inspect before acting.

### D5. Threshold calibration protocol (Q2)

The output is `evals/reports/leakage_calibration_<date>.json`.

1. **Planted positives (leak-like pairs), built from *train* records only**, so no test text is touched. Take 200 random train records and create one perturbed copy per record for each of five types:
   - `entity_swap`: names, companies, ids and amounts replaced from a scratch pool;
   - `drop_reorder`: 25% of sentences removed, the rest shuffled;
   - `typo`: 3–5% character noise;
   - `paraphrase`: rewritten by the Family A model with facts kept (Apache-2.0 output, train-side tooling only);
   - `style_transfer`: the same situation card re-generated in a different style.
   That gives 1,000 pairs.
2. **Hard negatives.** 2,000 cross-split pairs (train × test_synth) with the **same intent and product_area**. By construction their scenarios differ. Add 1,000 same-intent, different-area pairs.
3. **Natural pairs for human labels.** For each test_synth item, find its nearest train neighbor by cosine.
   - Stratify the neighbor pairs into bins [0.80, 0.84), [0.84, 0.88), [0.88, 0.90), [0.90, 0.92), [0.92, 0.94), [0.94, 0.96), [0.96, 1.0].
   - Sample up to 30 per bin.
   - The owner labels each pair *same underlying scenario* or *different scenario*, blind to the score.
4. **Decision rule.** On a 0.005 grid over [0.80, 0.99], choose τ_emb as the **smallest τ** such that:
   - the hard-negative flag rate is ≤ 1%;
   - projected train removals are ≤ 5% (the share of train records flagged against any protected item);
   - human-labeled natural pairs at or above τ have precision ≥ 0.5.

   Then report recall at τ for each planted type. The same procedure confirms the Jaccard 0.70 flag. Lower it toward 0.60 only if `entity_swap` recall is below 0.95 and the hard-negative rate stays ≤ 1%.
5. **Interpretation.** `entity_swap`, `typo` and `drop_reorder` should be caught by both checks. `paraphrase` and `style_transfer` rely on the embedding check. If their recall is below 0.8 at τ, record this as a residual risk; it is mitigated by `scenario_seed` and pool disjointness (C4).

### D6. Template-leakage controls and probes (Q3)

- **Prevention (C4):** P-A templates `pa.t1–t4` (train), `pa.t5–t6` (val) and `pb.*` (test) are disjoint. Both families are zero-shot, so there are no exemplars to share. Persona, company and scenario-seed pools are split-disjoint. Invoice ids carry a split prefix.
- **Probes (report only, reviewed at the P1 exit):**
  - *subject-only probe*: logistic regression on TF-IDF of train subjects, evaluated on test_synth subjects. If it is within 5 points of the full-text model, subjects leak the label; diversify `subject_style`.
  - *cue inspection*: the top 20 positive-weight n-grams per intent from a train bag-of-words logistic regression, inspected by hand for non-semantic cues (pool names, greetings, fact-sheet phrasing).
  - *keyword prevalence*: the share of each intent's tickets containing its canonical keyword, per split.
  - *prompt echo*: shared 8-grams between tickets and the generator prompt or fact-sheet text (report; drop if ≥ 1 per 20 tickets in an intent).

### D7. KB-overlap implementation (Q4)

- **Index.** Tokenize the markdown-stripped `body_md` of all KB versions after D1 normalization. Hash every 30-token window with blake2b-64: about 90k windows for 112 docs × ~800 tokens.
- **Scan.** Scan each record's `customer_text` windows. Any hit is a flag. For flagged records only, compute the longest common token run with `difflib.SequenceMatcher` and report it.
- **Agent messages.** Scan synthetic agent messages separately against `reply_template` docs; report only.

### D8. Handling policy (Q5)

| Situation | Before freeze (during P1) | After freeze (P1 exit onward) |
|---|---|---|
| Trainable × protected flag (C1–C3, C6) | Drop the trainable record; regenerate to refill the quota; re-run | Same (train can always change) |
| Duplicate within a protected split, or test_synth × test_hard | Keep the earlier/human record; replace the other from the same stratum | Not allowed. A new split version (`.v2`) is required, plus re-running E1–E6 with a note in results |
| KB copying in a protected split (C5) | Replace the record from the same stratum | As above |
| Structural overlap (C4) | Fix the generator; regenerate the affected trainable records | CI failure; the trainable side must change |
| v0.2 train additions (inspired by hard-set errors) | – | Re-run all checks against the frozen splits with **stricter** flags for that batch (char-5 J ≥ 0.50; cos ≥ τ_emb − 0.03) plus an owner attestation "not paraphrased from any test_hard item". Also apply the hard-set dev/final split (evaluation-statistics.md) |

- **Freeze.** At P1 exit, `test_synth.v1`, `test_hard.v1` and `test_ood.v1` are written with sha256 values in `data/manifests/<ver>.json`. CI verifies the hashes on every run.
- **Record keeping.** Every replacement is recorded as `{old_id, new_id, check, reason}` in the leakage report. Test items are never removed silently, and never removed because a model failed on them.

### D9. Report format and CI gate (Q6)

`evals/reports/leakage_<date>.json` is committed:

```json
{
  "report_version": "leakage.v1",
  "created_at": "2026-10-01T12:00:00Z", "git_sha": "<sha>", "manifest_sha256": "<sha>",
  "config": {
    "normalization": "nfkc|placeholders|lower|digits0|ws",
    "char_ngram": 5, "jaccard_flag": 0.70, "jaccard_report": 0.50,
    "lsh": {"num_perm": 128, "threshold": 0.5, "weights": [0.2, 0.8], "b": 30, "r": 4, "datasketch": "2.0.0"},
    "embedding": {"model": "BAAI/bge-small-en-v1.5", "revision": "<hf-sha>", "tau": 0.92,
                  "calibration_report": "evals/reports/leakage_calibration_2026-10-01.json"},
    "kb_window_tokens": 30
  },
  "counts": {"train~test_synth": {"C1": 0, "C2": 2, "C3": 5, "C5": 0, "C6": 0}},
  "flags": [{"check": "C3", "a": "tr_000123", "b": "ts_000456", "score": 0.941, "action": "drop_a"}],
  "replacements": [{"old_id": "ts_000789", "new_id": "ts_000901", "check": "C5", "reason": "31-token KB run"}],
  "disjointness": {"template_id": {}, "scenario_seed": {}, "persona_id": {}, "company_id": {}},
  "nn_similarity_quantiles": {"test_synth->train": {"p50": 0.71, "p95": 0.83, "p99": 0.88}},
  "gate": {"passed": true, "failures": []}
}
```

- **CI job `leakage`** runs on PRs touching `data/**` or `ml/src/tw_ml/datagen/**`, and nightly.
- **Gate:** after actions, zero C1–C3/C6 flags on trainable × protected pairs, zero C4 violations, zero C5 hits on protected splits, and manifest hashes matching.

### D10. Code sketch

`ml/src/tw_ml/datagen/leakage.py`. Pins to verify at build: `datasketch==2.0.0`, `sentence-transformers==6.1.0`, `scipy==1.18.*`, `numpy>=2`.

```python
"""Cross-split leakage and dedup checks. Research note: docs/research/leakage-and-dedup.md.

CLI: python -m tw_ml.datagen.leakage --manifest data/manifests/<ver>.json --out evals/reports/leakage_<date>.json
Exits 1 if the gate fails.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from scipy import sparse

TRAINABLE: tuple[str, ...] = ("train", "val")
PROTECTED: tuple[str, ...] = ("test_synth", "test_hard", "test_ood", "e2e_scenarios")

_PLACEHOLDER = re.compile(r"<(EMAIL|PERSON|PHONE|CARD_LAST4)_\d+>")
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Rec:
    record_id: str
    split: str
    customer_text: str          # subject + message + customer-authored prior messages (D1)
    template_id: str
    scenario_seed: int
    persona_id: str | None
    company_id: str | None


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = _PLACEHOLDER.sub(lambda m: f"<{m.group(1).lower()}>", t).lower()   # before lowercasing: regex is uppercase
    t = _DIGITS.sub("0", t)
    return _WS.sub(" ", t).strip()


def sha256_norm(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def char_shingles(text: str, n: int = 5) -> set[str]:
    t = normalize(text)
    return {t[i : i + n] for i in range(max(1, len(t) - n + 1))}


def tokens(text: str) -> list[str]:
    return _WORD.findall(normalize(text))


def _h64(parts: Sequence[str]) -> int:
    return int.from_bytes(hashlib.blake2b("\x1f".join(parts).encode(), digest_size=8).digest(), "big")


# ---------- C2: exact Jaccard (CI truth path) ----------
def exact_jaccard_cross(a: list[set[str]], b: list[set[str]], flag: float) -> list[tuple[int, int, float]]:
    """All (i, j, J) with J(a_i, b_j) >= flag, via a sparse intersection-count matrix."""
    vocab: dict[str, int] = {}

    def coo(sets: list[set[str]]) -> tuple[list[int], list[int]]:
        rows: list[int] = []
        cols: list[int] = []
        for r, s in enumerate(sets):
            for sh in s:
                cols.append(vocab.setdefault(sh, len(vocab)))
                rows.append(r)
        return rows, cols

    (ra, ca), (rb, cb) = coo(a), coo(b)          # both passes first, so the vocab is complete
    v = len(vocab)
    A = sparse.csr_matrix((np.ones(len(ra), np.int32), (ra, ca)), shape=(len(a), v))
    B = sparse.csr_matrix((np.ones(len(rb), np.int32), (rb, cb)), shape=(len(b), v))
    inter = (A @ B.T).tocoo()                     # chunk the rows of A if |a| x |b| grows large
    sa, sb = np.asarray(A.sum(1)).ravel(), np.asarray(B.sum(1)).ravel()
    jac = inter.data / (sa[inter.row] + sb[inter.col] - inter.data)
    keep = jac >= flag
    return list(zip(inter.row[keep].tolist(), inter.col[keep].tolist(), jac[keep].tolist()))


# ---------- C2/C7: MinHash-LSH candidates (scalable path) ----------
def lsh_candidates(a: list[set[str]], b: list[set[str]]) -> set[tuple[int, int]]:
    from datasketch import MinHash, MinHashLSH

    lsh = MinHashLSH(threshold=0.5, num_perm=128, weights=(0.2, 0.8))
    assert (lsh.b, lsh.r) == (30, 4), "datasketch optimizer changed; re-run the ERPROT S-curve table"
    enc = lambda sets: [[s.encode("utf-8") for s in sh] for sh in sets]  # noqa: E731
    for i, m in enumerate(MinHash.bulk(enc(a), num_perm=128, seed=1)):
        lsh.insert(f"a{i}", m)
    pairs: set[tuple[int, int]] = set()
    for j, m in enumerate(MinHash.bulk(enc(b), num_perm=128, seed=1)):
        pairs.update((int(k[1:]), j) for k in lsh.query(m))
    return pairs  # verify every candidate with exact Jaccard before flagging


def jaccard(x: set[str], y: set[str]) -> float:
    return len(x & y) / len(x | y) if (x or y) else 1.0


# ---------- C3: embeddings ----------
def embed(texts: list[str], model_id: str = "BAAI/bge-small-en-v1.5", revision: str | None = None) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_id, revision=revision, device="cpu")
    x = np.asarray(model.encode(texts, batch_size=64), dtype=np.float32)   # no query instruction (symmetric)
    return x / np.clip(np.linalg.norm(x, axis=1, keepdims=True), 1e-12, None)


def cosine_flags(e_prot: np.ndarray, e_train: np.ndarray, tau: float) -> list[tuple[int, int, float]]:
    s = e_prot @ e_train.T                         # (|protected|, |trainable|); ~5.3M floats here
    ii, jj = np.nonzero(s >= tau)
    return [(int(i), int(j), float(s[i, j])) for i, j in zip(ii, jj)]


# ---------- C5: KB copying ----------
def kb_window_index(kb_bodies: Iterable[str], n: int = 30) -> set[int]:
    idx: set[int] = set()
    for body in kb_bodies:
        t = tokens(body)
        idx.update(_h64(t[i : i + n]) for i in range(len(t) - n + 1))
    return idx


def kb_hits(text: str, index: set[int], n: int = 30) -> bool:
    t = tokens(text)
    return any(_h64(t[i : i + n]) in index for i in range(len(t) - n + 1))


def longest_run(text: str, kb_body: str) -> int:
    a, b = tokens(text), tokens(kb_body)
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size


# ---------- C4: structural disjointness ----------
def disjointness(recs: Sequence[Rec]) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for key in ("template_id", "scenario_seed", "persona_id", "company_id"):
        by: dict[str, set[str]] = defaultdict(set)
        for r in recs:
            v = getattr(r, key)
            if v is not None:
                by[r.split].add(str(v))
        viol = {
            f"{s}~{p}": sorted(by[s] & by[p])[:20]
            for s in TRAINABLE for p in PROTECTED if by[s] & by[p]
        }
        if by["train"] & by["val"] and key in ("template_id", "scenario_seed"):
            viol["train~val"] = sorted(by["train"] & by["val"])[:20]
        out[key] = viol
    return out


# ---------- policy ----------
def apply_policy(pairs: list[tuple[Rec, Rec, str, float]]) -> tuple[set[str], list[dict]]:
    """pairs: (a, b, check, score) with a trainable and b protected -> drop a; protected-protected -> replace b."""
    drop, replace = set(), []
    for a, b, check, score in pairs:
        if a.split in TRAINABLE:
            drop.add(a.record_id)
        elif a.split in PROTECTED and b.split in PROTECTED:
            replace.append({"old_id": b.record_id, "check": check, "score": round(score, 4),
                            "reason": "protected-protected duplicate; replace pre-freeze"})
    return drop, replace
```

Calibration helper sketch (`ml/src/tw_ml/datagen/leakage_calibrate.py`):

```python
from typing import Callable

import numpy as np


def choose_tau(pos: np.ndarray, hard_neg: np.ndarray, removal_at: Callable[[float], float],
               natural: list[tuple[float, bool]], grid=np.arange(0.80, 0.9901, 0.005)) -> dict:
    """pos/hard_neg: cosine scores of planted-leak pairs and hard-negative pairs.
    removal_at(t): share of train that would be dropped at t. natural: (score, human_says_leak)."""
    for t in grid:                                   # smallest feasible t = highest recall
        fp_rate = float((hard_neg >= t).mean())
        nat = [lab for s, lab in natural if s >= t]
        prec = (sum(nat) / len(nat)) if nat else 1.0
        if fp_rate <= 0.01 and removal_at(t) <= 0.05 and prec >= 0.5:
            return {"tau": round(float(t), 3), "recall_planted": float((pos >= t).mean()),
                    "hard_neg_flag_rate": fp_rate, "train_removal": removal_at(t), "natural_precision": prec}
    raise ValueError("no feasible tau; inspect distributions (topic similarity dominates)")
```

- **Unit tests** (`ml/tests/test_leakage.py`):
  - `normalize` is idempotent;
  - `exact_jaccard_cross` equals the brute-force `jaccard` on 50 random pairs;
  - the LSH band assertion holds;
  - a planted exact duplicate and a planted 31-token KB copy are both flagged;
  - disjointness detects an injected shared `template_id`.

---

## SPEC IMPACT (do not edit the spec here; raise via the ADR-0016 amendment)

| # | Spec text (§9.3) | Finding | Proposed change |
|---|---|---|---|
| SI-1 | "MinHash LSH (5-gram shingles, 128 perms), Jaccard ≥ 0.7 flagged" | datasketch defaults at t=0.7 give b=14, r=9, and **P(candidate \| J=0.7) = 0.44**, which is unacceptable for an audit. The shingle unit is ambiguous | LSH candidates at t=0.5 with w=(0.2, 0.8) (b=30, r=4), plus **exact Jaccard verification ≥ 0.70**; exact all-pairs is the CI truth at our scale; shingles are **char-5 on normalized text** |
| SI-2 | "embedding cosine ≥ 0.92 (bge-small) cross-split flagged" | The model card says to set thresholds from your own data's similarity distribution | 0.92 is a starting value; calibrate per D5; record τ and the calibration report in every leakage report |
| SI-3 | "flagged pairs are removed from train, never from test" | Silent on duplicates within a test split, test_synth × test_hard duplicates, and KB copying inside test | Before freeze: **replace** such test items from the same stratum, with logging. After freeze: immutable, new version required |
| SI-4 | "CI fails if any fire on the test splits" | Needs the val side and the e2e_scenarios, protected-string (C6) and structural (C4) checks to be explicit | Adopt the D2 table as the normative list |
| SI-5 | §16 "Hard-set failures inform new *train* data only" | Paraphrase leakage can evade thresholds, and adaptive reuse of test_hard biases its estimate even without textual overlap | Stricter thresholds + attestation for v0.2 batches (D8); hard-set dev/final split (evaluation-statistics.md SI-7) |

---

## IMPLEMENTATION CHECKLIST

- [ ] Pin `datasketch==2.0.0`, `sentence-transformers==6.1.0` and the bge-small HF revision SHA in `ml/uv.lock` and `ml/configs/leakage.yaml`.
- [ ] Implement `leakage.py` (D10) and `leakage_calibrate.py`; add the unit tests listed above.
- [ ] Run the D5 calibration once P1 data exists; commit `evals/reports/leakage_calibration_<date>.json`; set τ_emb (and confirm J=0.70) in `ml/configs/leakage.yaml`.
- [ ] Build the protected-string list (C6): spec §5.1 examples, §17 demo tickets, labeling-guideline examples, generator prompts and fact sheet. Store it in `data/spec/protected_strings.v1.txt`.
- [ ] `make leakage` target + CI job (D9 gate); nightly run.
- [ ] Freeze step at P1 exit: write the sha256 values of the protected splits into the manifest; CI hash check.
- [ ] Label-cue probes (D6) in the P1 exit report; dataset-card section "Leakage and shortcut audits".
- [ ] v0.2 procedure documented in `docs/eval/v0.2-data-procedure.md` (stricter flags + attestation).

---

## OPEN RISKS / TO VERIFY

| Risk / item | Status | Mitigation |
|---|---|---|
| Semantic leakage (the same scenario retold in new words) below both thresholds | Accepted, measured | Scenario-seed and pool disjointness (C4); planted `style_transfer` recall reported |
| Topic similarity driving over-removal from train | Open | 5% removal budget in D5; NN histograms; inspect before acting |
| Long tickets (> 512 tokens) truncated for embedding | Accepted | Lexical check covers the full text |
| datasketch 2.x optimizer or scheme changes | Mitigated | Pin; band assertion; never mix schemes |
| sentence-transformers 6.x `encode` keyword changes | UNVERIFIED | Manual L2 normalization; pin the version |
| Protected-string list incomplete (new spec examples added later) | Open | Regenerate the list from spec/guidelines in CI |
| bge-small is a retrieval model, not a paraphrase detector | Accepted | Calibration measures its paraphrase recall; a paraphrase model (e.g., a MiniLM paraphrase checkpoint) can be tested as an alternate in D5 |

---

## LINKED ADR

- **ADR-0016**: amend with SI-1 to SI-4 (the leakage method is part of the test-set design).
- **ADR-new "Evaluation statistics protocol"** (evaluation-statistics.md): hard-set dev/final split (SI-5).
- **Related ERPROT docs:** `synthetic-data-generation.md` (pools, templates, provenance), `bitext-ood-dataset.md` (dedup within the OOD sample), `hybrid-retrieval.md` (qrels built from test tickets).

---

## SOURCES (all accessed 2026-09-26)

- [L1] datasketch `lsh.py` (MinHashLSH signature, optimizer, weights validation). https://github.com/ekzhu/datasketch/blob/master/datasketch/lsh.py
- [L2] datasketch `minhash.py` (MinHash signature, `scheme` options, `bulk`/`generator`). https://github.com/ekzhu/datasketch/blob/master/datasketch/minhash.py
- [L3] datasketch on PyPI (version 2.0.0, MIT, Python ≥ 3.9, affine32 default note). https://pypi.org/project/datasketch/
- [L4] Hugging Face datatrove `MinhashConfig` defaults and threshold comment. https://github.com/huggingface/datatrove/blob/main/src/datatrove/pipeline/dedup/minhash.py
- [L5] Lee et al., "Deduplicating Training Data Makes Language Models Better", ACL 2022. https://arxiv.org/abs/2107.06499
- [L6] BAAI/bge-small-en-v1.5 model card (dimension, max length, similarity distribution, threshold advice, license). https://huggingface.co/BAAI/bge-small-en-v1.5
- [L7] sentence-transformers on PyPI (6.1.0, Apache-2.0). https://pypi.org/project/sentence-transformers/
- [L8] Gururangan et al., "Annotation Artifacts in Natural Language Inference Data", NAACL 2018. https://arxiv.org/abs/1803.02324

**Computation:** the S-curve table was produced during this research session by reimplementing datasketch's `_optimal_param` (the same objective, integrated with a composite Simpson rule because SciPy was not installed in the research environment). To reproduce with the pinned library, construct `MinHashLSH(threshold=..., num_perm=..., weights=...)`, read `.b`/`.r`, and evaluate 1 − (1 − s^r)^b. The D10 code sketch was exercised during this session for its pure-Python/NumPy parts: normalization, exact Jaccard vs brute force (checked with a dense stand-in for `scipy.sparse`), KB windows, disjointness and policy. That run found and fixed a normalization-order bug.

---

**Document Version**: 1.0
**Next Update**: after the D5 calibration on P1 data (fill in τ_emb; confirm or adjust the Jaccard flag)
