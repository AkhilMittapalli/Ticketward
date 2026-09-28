# data/ - provenance policy and layout

**Only synthetic, public, or authorized de-identified data may enter this repository or any
derived artifact** (safety rule S-12, BR-016, non-goal NG-02). Real customer tickets, e-mails,
names, card numbers or credentials are never collected, committed or used for training. Taskmoor
and every company, person, account and ticket are fictional ("Taskmoor is fictional and not
affiliated with any real company").

**No Claude/Anthropic output enters any dataset** (A-01): train/val come from
`openai/gpt-oss-120b` (Family A), test_synth from DeepSeek-V3.2 on DeepInfra (Family B, owner decision D-07), the hard set from the
owner's hand (no LLM assistance), and the OOD set from the public Bitext datasets. The code refuses
Anthropic endpoints and models, and every record's provenance is checked (T-DATA-provenance).

## Layout

| Path | Contents | Committed |
|---|---|---|
| `spec/generation_matrix.yaml` | generation matrix: quotas, marginals, plausibility constraints, pairwise coverage, strata minimums, per-intent card material | yes |
| `spec/fact_sheet.v1.md` | the only product facts a generator prompt may contain (plans, limits, features, error codes); no KB prose, no example tickets | yes |
| `spec/label_rules.v1.yaml` | §5.8 routing, critical/forced-review sets, priority guidance, churn and human-request QA lexicons | yes |
| `spec/pools/{train,val,test,hard}/` | split-disjoint fictional personas, companies, competitors and injection snippets (seeded; `pools.json` holds the seed); `brand_denylist.txt` | yes |
| `spec/protected_strings.txt` | spec examples, demo tickets and every labeling-guideline example; leakage check C6 keeps them out of all splits | yes |
| `spec/bitext_mapping.v1.yaml` | pinned Bitext sources, the normative T1/T2/probe/excluded mapping, the 500-item composition and placeholder fills | yes |
| `hard_set/TEMPLATE.jsonl` | one empty row with every hard-set field (the owner writes the cases in `evals/hard_set.v1.jsonl`, see `docs/hard_set_guide.md`) | yes |
| `manifests/<split>.json` | content-hash manifests (file SHA-256, record count, content digest, `val_dev` / `hard_dev` / `hard_final` subsets and seeds); frozen at the P1 exit | yes |
| `kb/` | knowledge-base markdown with front matter (written later in P1) | yes |
| `seed/`, `email_feed/` | synthetic accounts and demo users; simulated e-mail samples (later phases) | yes |
| `generated/<split>/` | generator output: `records.jsonl` (accepted), `quarantine.jsonl`, `costs.jsonl` (token ledger), `checkpoint.json`, `dry_run/` | **no** (gitignored; published as a private HF dataset) |
| `generated/test_ood/` | materialized Bitext text (CDLA-Sharing-1.0) | **no**: only row pointers are committed (`evals/ood/test_ood.v1.pointers.jsonl`) |
| `raw/`, `cache/`, `exports/` | scratch data | **no** |

## Provenance fields

Every record (`tw_ml.datagen.records.Provenance`, spec §9.1 step 8 + v1.1) carries:

| Field | Meaning |
|---|---|
| `record_id` | stable id with a split prefix (`tr_00042`, `ts_00007`, `th_001`, `to_0001`); it never encodes a label |
| `split` | `train`, `val`, `test_synth`, `test_hard`, `test_ood`, `e2e_scenarios` |
| `generator_family` | `openai_gpt_oss` (train/val), `deepseek` (test_synth; `mistral` stays valid as the config-only alternative), `human` (hard set, v0.2 additions), `public_bitext` (test_ood) |
| `generator_model` / `api_model_id` | the open-weights model id and the host's API id (e.g. `deepseek-ai/DeepSeek-V3.2` / `deepseek-ai/DeepSeek-V3.2` on DeepInfra); `generator_quantization` records the host's serving precision (`fp4`) |
| `provider`, `generator_endpoint` | host label (`deepinfra`, `groq`, `mistral` (alternative), `owner`, `huggingface`) and `host|model|request date` |
| `prompt_family`, `prompt_version`, `template_id` | `P-A` / `P-B`, the prompt file version (`pa_persona.v1`, `pb_scenario.v1`) and the template variant (`pa.t1`..`pa.t6`, `pb.s1+pb.m1`, `pb.s2+pb.m2`) |
| `cell_id`, `scenario_seed`, `persona_id`, `company_id` | the generation-matrix cell and the pool entries used (checked for split disjointness, C4) |
| `noise_ops` | masking and typo operations applied after generation |
| `seed`, `created_at` | matrix (or split) seed; UTC timestamp |
| `label_source` | `generator_proposed`, `human_verified`, `human_written` or `public_mapped` |
| `label_basis` | where the labels came from: `llm_proposal` (P-A), `scenario_spec` (P-B; the test generator never labels), `human`, `bitext_mapping` |
| `taxonomy_version`, `content_sha256` | `2026-09-v1`; SHA-256 of the normalized customer text |
| `terms_snapshot_id` | the vendor-terms snapshot in force (`docs/legal/generator-terms-2026-09-27.md`) |
| `llm_assisted`, `mapping_tier`, `probe`, `bitext` | hard-set attestation (`false`); OOD tier, probe and pinned row pointer |
| `reviewed_by`, `review_round`, `label_notes` | pseudonymous reviewer ids (`R-...`) and review history |

## Rules

- Personal data appears only as typed placeholders (`<EMAIL_1>`, `<PERSON_1>`, `<PHONE_1>`,
  `<CARD_LAST4_1>`), injected on purpose in about 20% of generated tickets; persona names are masked
  before a record is stored, and the rule-checker rejects raw e-mails, phones, cards, IBANs, URLs
  and secrets.
- The test splits are never used for training. Leakage checks C1-C7 (`python -m tw_ml.datagen
  leakage`) only ever drop **trainable** records; duplicates inside protected splits are replaced
  before the freeze, and after the freeze a changed test split is a new version.
- Generation needs a current vendor-terms snapshot (older than 30 days blocks a real run unless the
  owner re-reviews and passes `--terms-reviewed`) and stays inside the $15 budget (dated prices in
  `ml/configs/datagen_prices.v1.yaml`).
- If you find anything that looks like real personal data, stop and report it privately (see
  SECURITY.md).
