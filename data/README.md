# data/ - provenance policy

**Only synthetic, public, or authorized de-identified data may enter this repository or any
derived artifact** (safety rule S-12, BR-016, non-goal NG-02). Real customer tickets,
emails, names, card numbers or credentials are never collected, committed, or used for
training. Taskmoor and every company, account and ticket are fictional.

## Layout (populated from P1)

| Path | Contents | Tracked in git |
|---|---|---|
| `spec/` | `generation_matrix.yaml` (intent x product area x plan x channel x sentiment x difficulty x length x style) | yes |
| `kb/` | knowledge-base markdown sources with front-matter metadata (112 docs incl. 3 adversarial drafts) | yes |
| `seed/` | synthetic accounts (60 companies) and demo users per role | yes |
| `email_feed/` | simulated `.eml`/JSON feed for the email adapter | yes (small samples) |
| `manifests/` | content-hash manifests of every dataset version | yes |
| `raw/`, `generated/`, `cache/` | generated datasets (train/val/test) | **no**: published as HF Hub datasets |

## Required provenance fields

Every dataset record carries these fields (spec §9.1 step 8); CI rejects records without a
`generator_family` or a `public:<source>` origin (T-DATA-provenance):

| Field | Meaning |
|---|---|
| `record_id` | stable unique id |
| `split` | `train`, `val`, `test_synth`, `test_hard`, `test_ood`, `e2e_scenarios` |
| `generator_family` | model family that produced the text (Family A train/val, Family B test), `human` for the hard set, or `public:bitext` |
| `generator_model` | exact model id and version used |
| `prompt_family` | `P-A` (persona-based) or `P-B` (scenario-first) |
| `prompt_version` | version of the generation prompt |
| `seed` | generation seed |
| `created_at` | UTC timestamp |
| `label_source` | `generator_proposed`, `human_verified` or `human_written` |
| `taxonomy_version` | `2026-09-v1` |
| `content_sha256` | SHA-256 of the normalized ticket text |

## Rules

- Synthetic PII placeholders (`<EMAIL_1>`, `<PERSON_1>` ...) are injected on purpose in about
  20% of tickets; real-looking PII is not.
- The test splits are never used for training; leakage checks (exact hash, MinHash LSH,
  embedding similarity, template ids, KB overlap) run before any split is published, and
  flagged pairs are removed from train only.
- Generator terms of service are confirmed through ERPROT before generating training data.
- If you find anything that looks like real personal data, stop and report it privately
  (see SECURITY.md).
