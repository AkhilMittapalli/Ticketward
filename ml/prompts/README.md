# ml/prompts/ (placeholder)

Versioned prompt files, mirrored into the `prompt_versions` table by sha256 (spec §9.4).
A prompt is immutable once used by a published model or eval run: edits create a new
version (`triage.v2.txt`).

| Planned file | Used by | Phase |
|---|---|---|
| `triage.v1.txt` | SLM triage (`TriageModelOutput`, JSON-schema constrained) | P2 |
| `draft.v1.txt` | grounded drafting with numbered `<source id=n>` blocks | P6 |
| `handoff.v1.txt` | `one_line_summary` / `customer_problem` of handoff briefs | P7 |

Prompts contain no secrets (LLM07) and always wrap ticket text in `<ticket>` delimiters
labeled untrusted (LLM01).
