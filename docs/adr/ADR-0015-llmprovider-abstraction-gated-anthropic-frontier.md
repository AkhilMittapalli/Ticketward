---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §2, §6, §8, §14; spec §6.6, §7.1, §7.5, §9.7 (E6), §12.4, §12.6, §12.11, §13 S-07/S-08, §20 L-03/L-15, §24.3; research frontier-provider-anthropic
informed: admin persona (vendor-review acknowledgement); contributors
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0015: `LLMProvider` port with a gated Anthropic frontier adapter

> **Amended in spec v1.1 (2026-09-27; change record A-18, A-01, A-25(d)).**
> * **Default model `claude-sonnet-5`** (`TW_FRONTIER_MODEL`). Startup fails if the id is not returned by the
>   Models API. `claude-opus-5-5` is an optional E6 quality reference only. Claude Haiku 4.5 is not used (retirement
>   "not sooner than 2026-10-15").
> * **Request shape:**
>   * tool-less structured output (`output_config.format` json_schema via `messages.parse` with `DraftModelOutput`);
>   * `thinking={"type": "disabled"}`;
>   * **no `temperature` or other sampling parameters** (current models reject them);
>   * `max_tokens=800`;
>   * effort left at the default and swept in E6.
> * **Timeouts:** 9 s per attempt, 1 retry (`max_retries=1`), inside a 20 s overall deadline.
> * **Spend-limit errors open the budget breaker** and are never retried: HTTP 429 `enforced_spend_limit_reached`, or
>   HTTP 400 "usage limits". The frontier stays off until the next UTC day or month, with an alert.
> * The frontier gets a **dedicated workspace** with its own spend limit and a workspace-scoped key, a dated price
>   table, and server-side validation (the API grammar does not enforce `maxLength`, `maxItems` or numeric bounds).
> * **Never used as training data** (A-01, ADR-0031). All calls go through the **egress proxy** (ADR-0036).

## Context and Problem Statement

The brief wants a **provider-agnostic** frontier interface (brief §8). The frontier is used only for "complex
cross-document synthesis, if policy allows, never as an excuse for missing evidence" (brief §6), and it must comply
with privacy, security and vendor-review policies (brief §14, L-03).

The same port covers:
* the local SLM (Ollama);
* a vLLM stub;
* the rules baseline;
* a deterministic stub for CI.

Rule P10 selects the frontier only if **all** §7.5 conditions hold:
1. `frontier_enabled` and a recorded vendor-review acknowledgement;
2. intent not security/privacy-legal, no terminal P1–P9, and no P0, N5 or N6 reason;
3. evidence exists (P9 did not fire);
4. complexity score ≥ 2 (the only definition, §7.5);
5. the worst-case call cost ≤ $0.05 and fits the remaining daily budget (default $2.00; demo $1.00);
6. no residual PII hit ≥ 0.6.

E6 (frontier-only, 120 tickets, synthetic data) is the cost/quality reference, and E5's blended cost must be ≤ 20% of
E6 (M-10).

How should providers be abstracted, and how exactly is the frontier adapter configured and constrained?

## Decision Drivers

* Provider independence at the service layer: services depend on the port, never on a vendor SDK.
* Safety: masked-only input, sensitive-intent denylist, evidence required, no tools (S-07, S-08; LLM03:2026 excessive
  agency).
* Cost control: worst-case pre-check, daily budget, per-ticket cap, workspace spend limit, breaker
  (LLM06:2026 unbounded consumption).
* Correct handling of current API behaviour: sampling parameters rejected, thinking on by default, refusals, and
  spend-limit error shapes.
* Vendor-terms compliance: no training on outputs; retention confirmed in the vendor review.

## Considered Options

1. `LLMProvider` port with Anthropic as the first frontier adapter, gated by §7.5 (chosen)
2. OpenAI as the first frontier adapter
3. LiteLLM proxy as a multi-provider gateway
4. None (no frontier path)

## Decision Outcome

Chosen option: "`LLMProvider` port + gated Anthropic adapter", because the port satisfies the provider-agnostic
requirement in code, and the six-condition gate implements the brief's policy exactly. Tool-less native structured
output fits the no-agency rule.

Adapter configuration (spec §7.5; **all vendor specifics are verify-at-build and dated**):

| Aspect | Setting |
|---|---|
| Model | `claude-sonnet-5` default ($2 / $10 per MTok as of 2026-09-26; retirement "not sooner than" 2027-06-30); id checked against the Models API at startup |
| Output | `output_config.format` json_schema via `messages.parse(DraftModelOutput)`; the §6.6 validator still runs; `stop_reason == "refusal"` → local draft or human |
| Sampling | none sent; the port's `temperature` is ignored by this adapter |
| Thinking | disabled (Sonnet 5 thinks by default, and thinking tokens count toward `max_tokens`) |
| Tokens | `max_tokens=800` (the newer tokenizer produces about 30% more tokens; the `max_tokens` stop rate is re-measured in E6) |
| Timeouts | 9 s per attempt, `max_retries=1`, overall `asyncio.timeout(20)` |
| Breaker | connection errors, 5xx and ordinary 429s: 5 failures / 60 s opens it for 120 s → local draft |
| Budget | spend-limit errors open the budget breaker (no retry, no breaker count), frontier off until the next UTC day/month, alert; actual cost booked from `usage` |
| Account | dedicated workspace with a monthly spend limit and alert, lower rate limits, workspace-scoped key in the secret store |
| Pricing | dated price table in `providers/pricing.py` and `docs/`, re-checked before any budget decision (L-15) |
| Data | masked ticket text + chunk text only; retention confirmed in writing during vendor review; Batch API only for synthetic E6; outputs never used as training data |
| Network | via the egress proxy (only `api.anthropic.com` allowed); `anthropic` 1.x uses `httpx2` transitively, while the repo keeps `httpx` |

### Consequences

* Good, because services, eval and CI are provider-neutral, and the stub provider makes CI and Playwright
  deterministic.
* Good, because the frontier cannot excuse missing evidence, see sensitive or injection-flagged or PII-heavy tickets,
  act (no tools), or overspend (worst-case pre-check, breaker, workspace limit).
* Good, because E6 gives an honest cost/quality reference without contaminating training data (A-01).
* Bad, because the adapter encodes fast-moving vendor behaviour (sampling rejection, thinking defaults, error
  shapes). Mitigations: dated config, the startup model check, and per-phase re-verification.
* Bad, because frontier outputs are not temperature-deterministic, so evals use recorded cassettes (§6.6).
* Bad, because a public-demo key is an abuse target (R-09). Mitigations: off by default, $1/day demo cap, workspace
  limit, rate limits, `DEMO_LOCKED` org settings, and the egress allow-list.

### Confirmation

* `T-ROUTE-frontier` (all six conditions, table-driven), `T-ROUTE-no-evidence-no-frontier`,
  `T-ROUTE-frontier-denylist` (incl. the P0/N5/N6 bans), `T-ROUTE-local`.
* Config gate test (BR-074): no frontier without `frontier_enabled` and `vendor_review_ack_at`.
* `T-SEC-FRONTIER-budget`: the worst-case pre-check, daily cap, spend-limit error handling (no retry, breaker open,
  alert) and `frontier.budget_exhausted` audit.
* `T-SEC-FRONTIER-no-tools` (proposed name): the adapter never sends `tools`, `tool_choice` or sampling parameters.
  A startup test fails on an unknown model id.
* `T-SEC-PII-residual-gate`, and a span-attribute test proving only masked text leaves (§17 case 2 trace view).
* The data-provenance CI job: no Anthropic-produced record in any training export (A-01).
* M-10 and the E5 ≤ 20% of E6 ratio with a paired bootstrap CI. `tw_frontier_budget_remaining_usd` and
  `tw_frontier_breaker_state` alerts.

## Pros and Cons of the Options

### Port + gated Anthropic adapter

* Good, because it is provider-agnostic by construction, with tool-less structured output, workspace spend controls
  and one vendor review covering both E6 and the P7 frontier.
* Bad, because the optional path has a vendor dependency, the vendor behaviour changes quickly, and a vendor review
  is needed before enabling it.

### OpenAI first

* Good, because it is equally capable, with structured outputs.
* Bad, because it offers no functional advantage and needs a second vendor review. It remains a possible adapter.

### LiteLLM proxy

* Good, because it offers one API for many providers, with budgets.
* Bad, because it is an extra service and a large dependency surface. It duplicates our budget and breaker logic, and
  can hide provider-specific safety behaviour.

### None

* Good, because it has zero egress, spend and vendor review.
* Bad, because it drops brief requirements (BR-009, BR-033) and the E6 reference behind the central claim.

## More Information

* Spec (private): §6.6 (frontier outputs validated), §7.1, §7.5 (conditions, call settings), §7.7, §9.7 (E6), §9.8
  (M-09, M-10), §10, §12.4, §12.6 (workspace key), §12.11 (egress), §13 S-07, S-08, §20 L-03, L-15, §24.3 ($1/day).
  Change record A-18, A-01, A-25 (d).
* Brief (private): §2, §6, §8, §14. BR-009, BR-033, BR-049, BR-074.
* Research: [frontier-provider-anthropic](../research/frontier-provider-anthropic.md).
* Related ADRs: ADR-0010, ADR-0014, ADR-0019, ADR-0024, ADR-0031, ADR-0035, ADR-0036.
* Revisit when: a second vendor is needed, vendor terms change (retention, availability, model retirement), or the
  demo shows sustained budget pressure.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (`claude-sonnet-5`, no sampling,
  thinking off, 800 tokens, 9 s × 2 / 20 s, spend-limit breaker, dedicated workspace, egress proxy).
