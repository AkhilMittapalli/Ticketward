# ml/prompts/

Versioned prompt files, mirrored into the `prompt_versions` table by sha256 (spec §9.4). A
prompt is immutable once used by a published dataset, model or eval run: edits create a new
version (`pa_persona.v2.txt`, `triage.v2.txt`).

## Generator prompts (`datagen/`, P1)

| File | Family | Templates | Used for |
|---|---|---|---|
| `datagen/pa_persona.v1.txt` | P-A persona-first, one call per ticket, returns ticket + proposed labels + self-check | `pa.t1`-`pa.t4` (train), `pa.t5`-`pa.t6` (val) | Family A (`openai/gpt-oss-120b`) |
| `datagen/pb_scenario.v1.txt` | P-B scenario-first, two stages (case timeline, then the customer's message); **never asks for labels** | `pb.s1+pb.m1`, `pb.s2+pb.m2` | Family B (`deepseek-ai/DeepSeek-V3.2` on DeepInfra, D-07), test_synth |

Rules (spec §9.1, ERPROT `synthetic-data-generation` D6):

* zero-shot: the only product context is `data/spec/fact_sheet.v1.md`; no knowledge-base text
  and no example tickets ever appear in a generator prompt;
* placeholders are `{{name}}`; `tw_ml.datagen.prompts` renders them deterministically from the
  plan cell, and a template with an unknown placeholder fails;
* template ids are recorded as `template_id` and must be disjoint between splits (leakage C4);
* the static prompt text is also scanned by the report-only prompt-echo probe.

## Triage prompt (`triage.v1.txt`, P2)

The SLM triage prompt (spec §9.4), rendered by `tw_ml.prompts` for E3 zero-shot, the SFT targets
(P3) and the serving parity tests (P4):

* a **static system section**: role, the untrusted-data rule, the key list in output order, every
  intent with its definition and default queue/action, and the labeling rules with every enum
  value of the decoding schema. It is byte-identical for every request, so a serving prefix cache
  can reuse it. About 5.8K characters (roughly 1.2-1.5K tokens, tokenizer-dependent; the spec
  estimated ~350);
* a **user section** with `{{metadata_json}}` (one JSON line: tier, channel, product-area hint,
  received_at), `{{nonce}}` (the per-request delimiter id of `<ticket-{nonce}>`, A-16) and
  `{{ticket}}` (subject, earlier messages oldest first, latest message);
* the renderer neutralizes special-token literals and `<ticket-` tags in ticket text (`<` becomes
  `&lt;`), refuses a nonce that occurs in the ticket, and returns the target as minified
  `TriageLabels` JSON in decoding-schema key order. `tests/test_triage_prompt.py` checks that
  every model-facing taxonomy value appears in the system text.

## Planned

| File | Used by | Phase |
|---|---|---|
| `draft.v1.txt` | grounded drafting with numbered `<source id=n>` blocks | P6 |
| `handoff.v1.txt` | `one_line_summary` / `customer_problem` of handoff briefs | P7 |

Prompts contain no secrets (LLM07) and always wrap ticket text in `<ticket>` delimiters labeled
untrusted (LLM01).
