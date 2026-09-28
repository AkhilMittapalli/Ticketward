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

## Planned

| File | Used by | Phase |
|---|---|---|
| `triage.v1.txt` | SLM triage (`TriageModelOutput`, JSON-schema constrained) | P2 |
| `draft.v1.txt` | grounded drafting with numbered `<source id=n>` blocks | P6 |
| `handoff.v1.txt` | `one_line_summary` / `customer_problem` of handoff briefs | P7 |

Prompts contain no secrets (LLM07) and always wrap ticket text in `<ticket>` delimiters labeled
untrusted (LLM01).
