# Frontier Provider: Anthropic Claude - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-26
**Status**: Resolved for research. Model IDs, pricing, rate limits, retention/ZDR, structured outputs, spend controls and SDK behaviour were verified against Anthropic's official docs on 2026-09-26. Owner actions remain for the L-03 vendor-review sign-off (checklist D6). These include confirming the default API retention period with Anthropic (D6 #3), because two official Anthropic pages word it differently.
**Category**: Vendor / LLM provider (frontier fallback)
**Linked ADR(s)**: ADR-0015 (LLMProvider abstraction; Anthropic as the first frontier adapter; gated)
**Spec sections**: §6.6, §7.1 (`LLMProvider`), §7.5, §7.7, §9.1 (generator ToS), §9.7 E6, §9.8 M-10, §11 (`/admin/org-settings`), §12.6, §15 (cost metrics), §20 L-03/L-15, §21 R-09, §23
**Method**: ERPROT §0. Official Anthropic docs (platform.claude.com), privacy center, legal pages, the official Python SDK repo and PyPI. The model IDs and prices reported by the environment were **checked against the official pages, not taken on trust**. All accessed 2026-09-26.

---

## EXECUTIVE SUMMARY

1. **The environment's lineup is confirmed by the official models overview and pricing pages.**
   - **Claude Opus 5.5**: `claude-opus-5-5`, $4 / $20 per MTok, released 2026-09-22.
   - **Claude Sonnet 5**: `claude-sonnet-5`, $2 / $10, released 2026-06-30. The pricing page says the introductory $2/$10 "is now the standard price. The previously scheduled increase … will not occur."
   - **Claude Haiku 4.5**: `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`), $1 / $5, 200K context.
   - Claude Fable 5.1 ($10/$50) is the top tier and a "Covered Model": 30-day retention is mandatory and ZDR is unavailable unless Anthropic expressly authorizes it.
2. **Recommendation: `FRONTIER_MODEL = claude-sonnet-5`** for complex drafts.
   - A typical complex draft costs about **$0.013**. The worst case (6k-token ticket, 800 output tokens) is about **$0.026**. Both are inside the $0.05 per-ticket cap, and the $2/day budget covers about 149 typical drafts.
   - Sonnet 5 supports ZDR, structured outputs and `inference_geo`, and its retirement floor is 2027-06-30.
   - **Haiku 4.5 is not recommended.** Its retirement is "not sooner than **October 15, 2026**" (19 days away; no deprecation notice yet, under a ≥60-day notice policy). It also lacks `effort` and `inference_geo`, and needs 4,096 tokens to cache.
   - **Opus 5.5** is only an optional quality reference for E6. Thinking cannot be disabled on it, so output cost is less predictable against a 600–800-token cap.
3. **The adapter must handle several 2026 API changes** (all in Spec impact).
   - `temperature`/`top_p`/`top_k` return **400** on Claude 4.7+ models (including Sonnet 5 and Opus 5.5), and the Python SDK ≥1.0 **removed them** entirely (passing one raises `TypeError`).
   - **Sonnet 5 runs adaptive thinking by default**, and thinking tokens "count toward `max_tokens`" and are billed as output, so pass `thinking={"type": "disabled"}`.
   - Assistant prefill returns 400.
   - A new tokenizer produces "approximately 30% more tokens" than Sonnet 4.6.
   - SDK defaults are a **10-minute timeout and 2 retries**, and timeouts themselves are retried.
4. **Tool-less JSON is GA.** Use `output_config.format` = `json_schema`, or the Python helper `client.messages.parse(output_format=PydanticModel)`, which fits "no tools / no excessive agency". Limitations: no `minLength`/`maxLength`/`pattern`/`minimum`/`maximum` in the grammar (the SDK strips them and validates client-side), `additionalProperties` must be `false`, and no recursion. The schema is cached for up to 24 h.
5. **Data handling needs one clarification from Anthropic.** The privacy center (updated 2026-07-01) says API inputs and outputs are deleted "within 30 days". The docs retention page says conversation content "is not retained by default" apart from Covered Models. **Confirm the default with Anthropic** during L-03.
   - ZDR is available by agreement ("contact the Anthropic sales team"), per organization. The **Batch API is not ZDR-eligible** (29-day retention).
   - Flagged content can be retained for up to 2 years.
   - The Commercial Terms say "Anthropic may not train models on Customer Content from Services."
6. **Restriction in the other direction: we may not train on Claude outputs.** The Usage Policy (effective 2025-09-15) prohibits "Utilization of inputs and outputs to train an AI model" without prior authorization. Claude therefore cannot be spec §9.1's Family A training-data generator. It is used for frontier drafts and E6 evaluation only (SI-7; consistent with `synthetic-data-generation.md`).

---

## QUESTIONS

| # | Question (spec §23 + implementer needs) | Answered in |
|---|---|---|
| Q1 | What are the current model IDs and pricing (verify the environment's claim)? | F1 |
| Q2 | Is there structured output or another tool-less JSON approach? | F3, D2 |
| Q3 | What are the rate limits? | F4 |
| Q4 | What are the data-retention and zero-data-retention options? | F6 |
| Q5 | How do spend limits and workspaces work? | F5, D5 |
| Q6 | How should the Python SDK be used with timeouts and retries? | F8, D3 |
| Q7 | What goes in the vendor-review checklist for L-03? | F7, D6 |
| Q8 | Which model should handle complex drafts, versus cost? | F1, F2, D1, D8 |

---

## FINDINGS

All links below were accessed 2026-09-26.

### F1. Current models (from the [models overview](https://platform.claude.com/docs/en/about-claude/models/overview), [pricing](https://platform.claude.com/docs/en/about-claude/pricing), [deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) and per-model pages)

| | **Claude Sonnet 5** | Claude Opus 5.5 | Claude Haiku 4.5 |
|---|---|---|---|
| Claude API ID (alias) | `claude-sonnet-5` | `claude-opus-5-5` | `claude-haiku-4-5-20251001` (`claude-haiku-4-5`) |
| Input / output per MTok | **$2 / $10** | $4 / $20 | $1 / $5 |
| Cache write 5 m / 1 h; cache read | $2.50 / $4; $0.20 | $5 / $8; $0.20 (0.05×) | $1.25 / $2; $0.10 |
| Batch (−50%) in / out | $1 / $5 | $2 / $10 | $0.50 / $2.50 |
| Context / max output | 1M / 128K | 1M / 128K | 200K / 64K |
| Thinking | Adaptive, **on by default**; `{"type": "disabled"}` accepted | Adaptive, **always on**; `disabled` → 400 | Extended (manual `budget_tokens`), off by default |
| Default effort | `high` | `medium` | not supported |
| Sampling params | non-default → **400** | → 400 | accepted by the API, but the Python SDK 1.x has no parameter (use `extra_body`) |
| Assistant prefill | 400 | 400 | — |
| Min cacheable prompt | 1,024 tokens | 512 tokens | 4,096 tokens |
| `inference_geo` | yes (4.6+) | yes | **no** (400) |
| Reliable knowledge cutoff | Jan 2026 | Jun 2026 | Feb 2025 |
| Released | 2026-06-30 | 2026-09-22 | snapshot dated 2025-10-01 (per its ID; release date not re-checked) |
| Retirement ("not sooner than") | 2027-06-30 | 2027-09-22 | **2026-10-15** |
| ZDR | "supports zero data retention for organizations with ZDR agreements" | not a Covered Model, so ZDR by agreement | by agreement |

Other notes:
- "Every Claude model ID is a pinned snapshot, including the dateless IDs used from the 4.6 generation on."
- Anthropic gives "at least 60 days' notice before model retirement for publicly released models."
- Tokenizer: Claude 4.7-and-later models "produce approximately 30% more tokens for the same text".
- Sonnet 5 adds real-time cyber safeguards: refusals come back as HTTP 200 with `stop_reason: "refusal"`.

### F2. Behaviour that matters for the adapter

- **Thinking cost**: "the tokens Claude spends reasoning are billed as output tokens … and they count toward `max_tokens` alongside the response text" ([thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)).
- **Disabling thinking on Sonnet 5**: "To turn thinking off, pass `thinking: {type: "disabled"}`. Because `max_tokens` is a hard limit on total output … revisit it" ([what's new in Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5)).
- **Effort**: set with `output_config.effort` ∈ {low, medium, high, xhigh, max}. It "affects **all tokens** in the response" and "works whether or not thinking is enabled". For Sonnet 5, "Medium effort: Cost-saving step-down from the default" ([effort](https://platform.claude.com/docs/en/build-with-claude/effort)).
- **Sampling parameters**: the deprecations page lists them as "Deprecated (Claude Opus 4.7 and later) … Returns a 400 error when set to a non-default value". It adds: "The Python SDK (v1.0 and later) removes `temperature`, `top_p`, and `top_k`, so passing them raises a `TypeError`." The SDK [MIGRATION.md](https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md) points to `extra_body` for older models that still use them.
- **Stop reasons**: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal`. `stop_details` is populated only for refusals.

### F3. Structured outputs ([docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs))

- **GA, no beta header.** Request `output_config: {format: {type: "json_schema", schema: {...}}}`. The old `output_format` request parameter is deprecated. The Python helper `client.messages.parse(..., output_format=PydanticModel)` returns `response.parsed_output`. Supported models include `claude-sonnet-5`, `claude-opus-5-5` and `claude-haiku-4-5-20251001`.
- **Schema support**: basic types, `enum` of primitives, `const`, `anyOf`, `allOf`, local `$ref`/`$defs`, some string formats, and `minItems` of 0 or 1 only.
- **Not supported**: recursive schemas; numeric constraints; string constraints (`minLength`, `maxLength`, `pattern`), which the SDK moves into descriptions and "validate[s] … client-side"; and `additionalProperties: true`.
- **Performance**: grammar compilation adds latency on first use, and grammars are "cached for 24 hours".
- **Edge case**: on a refusal, or when `max_tokens` is too small, output "may not conform to the schema".
- **ZDR**: "Yes (qualified)". Only the schema is cached, for up to 24 h. The HIPAA section warns never to put sensitive data in schemas. Ours hold only enum vocabularies.
- Structured outputs are **tool-less**, which keeps §7.5's "no tools or function calling" (OWASP LLM06:2025 / LLM03:2026).

### F4. Rate limits ([rate limits](https://platform.claude.com/docs/en/api/rate-limits))

- Tiers are now **Start, Build, Scale and Custom**. New or low-history organizations "may start in the Evaluation tier" with lower limits.
- Limits are per model class, as requests per minute (RPM), input tokens per minute (ITPM) and output tokens per minute (OTPM). The algorithm is a token bucket, and a 429 includes `retry-after`. There are also "acceleration limits" on sharp ramps.
- Standard limits for Sonnet 5, Opus 5.5 and Haiku 4.5 (each model has its own bucket):

| Tier | RPM | ITPM | OTPM |
|---|---|---|---|
| Start | 1,000 | 2,000,000 | 400,000 |
| Build | 5,000 | 5,000,000 | 1,000,000 |
| Scale | 10,000 | 10,000,000 | 2,000,000 |

- **Cache-aware ITPM:** "only uncached input tokens count toward your ITPM" for these models.
- Response headers: `anthropic-ratelimit-{requests,tokens,input-tokens,output-tokens}-{limit,remaining,reset}` and `anthropic-workspace-id`.
- Batch API limits are separate (for example, Start tier allows 200,000 queued requests).

### F5. Spend controls and workspaces ([rate limits](https://platform.claude.com/docs/en/api/rate-limits), [workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces))

- **Monthly spend caps by tier:** Start $500, Build $1,000, Scale $200,000. Reaching the cap returns **HTTP 429 `rate_limit_error` with `details.error_code = "enforced_spend_limit_reached"` and no `retry-after`**. "Retrying, including the SDKs' automatic retries, fails until access resumes."
- **Your own spend limit** (org or workspace) returns **HTTP 400 `invalid_request_error`**, with a message beginning "You have reached your specified API usage limits" or "…specified workspace API usage limits".
- **Workspaces:**
  - Up to 100 per organization.
  - API keys can be scoped to one workspace.
  - Each workspace can have its own **spend limits (monthly cap plus alerts) and rate limits**. "You cannot set limits on the Default Workspace", and workspace limits cannot exceed the organization's.
  - Prompt caches are isolated per workspace.
  - Usage and cost can be reported per workspace through the Usage and Cost Admin API, which needs an Admin API key.

### F6. Data retention and privacy

- **Privacy center** ([article 7996866](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), last updated 2026-07-01): Anthropic will "automatically delete inputs and outputs on our backend within 30 days of receipt or generation". The exceptions are longer-retention services under user control (such as the Files API), custom agreements (ZDR), flagged content ("retain inputs and outputs for up to 2 years and trust and safety classification scores for up to 7 years if your chat is flagged") and legal requirements. Feedback submissions are kept for 5 years.
- **Docs** ([API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)):
  - "Retained data is never used for model training without your express permission."
  - "Conversation content (your prompts and Claude's outputs) is not retained by default; the exception is Covered Models, which require 30-day retention." **This reads differently from the 30-day statement above. Confirm with Anthropic** (D6).
  - ZDR means "Anthropic does not store customer prompts or responses at rest after the API response is returned". It covers the Messages and Token Counting APIs for eligible features and is enabled **per organization** through sales.
  - ZDR does not cover the Console/playground, Managed Agents, **Batch (29-day retention)**, code execution or CORS, among others.
  - Covered Models (Fable 5.1, Mythos 5.1, Fable 5, Mythos 5) require 30-day retention.
- **Data residency** ([data residency](https://platform.claude.com/docs/en/manage-claude/data-residency)):
  - `inference_geo: "global"` is the default; `"us"` keeps inference in the US at **1.1×** pricing (4.6+ models).
  - Workspaces can restrict geos with `allowed_inference_geos` and set a `default_inference_geo`.
  - "Workspace geo" (storage at rest) is currently `"us"` only and cannot be changed after the workspace is created.
  - Rate limits are shared across geos.

### F7. Legal and compliance evidence (for L-03)

- **Commercial Terms** (page shows effective 2025-06-17) ([link](https://www.anthropic.com/legal/commercial-terms)):
  - "Anthropic may not train models on Customer Content from Services."
  - The customer owns outputs.
  - Customers may not use the Services "to build a competing product or service, including to train competing AI models".
  - The Usage Policy is incorporated by reference.
- **Usage Policy** (effective 2025-09-15) ([link](https://www.anthropic.com/legal/aup)), under "Do Not Abuse our Platform": "Utilization of inputs and outputs to train an AI model (e.g., 'model scraping' or 'model distillation')" is prohibited without prior authorization from Anthropic. **This is stricter than the "competing models" clause**, because it covers training *any* AI model, including our triage SLM, on Claude outputs. `synthetic-data-generation.md` reaches the same conclusion and moves Family A to an open-weights generator, keeping Claude for evaluation only (E6).
- **DPA** (effective 2025-02-24) ([link](https://www.anthropic.com/legal/data-processing-addendum)):
  - Customer is controller and Anthropic is processor.
  - New subprocessors get reasonable notice and a **15-day objection window**. The list is at https://trust.anthropic.com/subprocessors (www.anthropic.com/subprocessors redirects there).
  - Transfers use SCCs (Modules 2 and 3), the UK Addendum and the Swiss Addendum.
  - Security: AES-256 at rest and TLS 1.2+ in transit.
  - Breach notice "within 48 hours".
  - Data is returned or deleted within 30 days of termination.
  - SOC 2 reports are available through the Trust Center.
- **Certifications** ([privacy center 10015870](https://privacy.claude.com/en/articles/10015870-what-certifications-has-anthropic-obtained), published 2026-03-16): HIPAA-ready configuration (BAA available), ISO 27001:2022, ISO/IEC 42001:2023, SOC 2 Type I and II. Reports are available through https://trust.anthropic.com.

### F8. Python SDK ([PyPI](https://pypi.org/pypi/anthropic/json), [SDK docs](https://platform.claude.com/docs/en/api/sdks/python), [MIGRATION.md](https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md))

- `anthropic` **1.8.0** is the latest release, MIT-licensed, Python ≥3.10. The 1.x line is "built on `httpx2`", an API-compatible fork of `httpx` maintained by the Pydantic team. Objects passed in (timeouts, clients) must come from `httpx2`. OSV lists no vulnerabilities for 1.8.0.
- **Retries**: "Certain errors are automatically retried 2 times by default, with a short exponential backoff". The retried errors are connection errors, 408, 409, 429 and ≥500.
- **Timeouts**: "By default requests time out after 10 minutes … Note that requests that time out are retried twice by default." A timeout raises `APITimeoutError`.
- **Errors**: `BadRequestError` 400, `AuthenticationError` 401, `PermissionDeniedError` 403, `NotFoundError` 404, `ConflictError` 409, `UnprocessableEntityError` 422, `RateLimitError` 429, `InternalServerError` ≥500, `APIConnectionError`. `APIStatusError` subclasses expose `.type` (for example `rate_limit_error`, `overloaded_error`).
- Every response has `_request_id` (public). `with_options(...)` sets per-request overrides. `AsyncAnthropic` is available, optionally with `DefaultAioHttpClient`.
- `client.messages.count_tokens(...)` estimates cost before sending.

---

## DECISION / RECOMMENDATION

**D1 Model: `claude-sonnet-5`, configured as `FRONTIER_MODEL`.** At startup, fail if the ID is not in `client.models.list()`. The Models API returns `max_input_tokens`, `max_tokens` and `capabilities`. `claude-opus-5-5` is an optional E6 reference only. Haiku 4.5 is excluded (F1).

**D2 Request shape (complex draft).**
- Tool-less structured output (`DraftModelOutput`).
- `thinking={"type": "disabled"}`.
- **No sampling parameters.** Determinism comes from the recorded cassette plus the prompt version, not from temperature.
- `max_tokens=800` in place of the spec's 600, to allow for the ~30% tokenizer growth. Re-check the `stop_reason == "max_tokens"` rate in E6.
- Effort: start at the default and sweep {low, medium, high} in E6. Choose by citation-support precision (M-06) per dollar.
- Masked text and chunk texts only (§7.5).
- `inference_geo` left at the default (`global`). Set `"us"` at 1.1× only if a residency requirement appears in L-03.

**D3 Adapter (async; per-attempt timeout; one retry; hard stage deadline; spend-limit aware).**

```python
# backend/src/ticketward/providers/anthropic.py (sketch; names per the SDK docs, verify at build)
from __future__ import annotations

import asyncio
from decimal import Decimal

import anthropic
import httpx2
from pydantic import BaseModel

# $/MTok, source: platform.claude.com/docs/en/about-claude/pricing (accessed 2026-09-26) - config table, dated
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
}


class FrontierBudgetExhausted(Exception): ...   # open breaker until budget reset / month start
class FrontierUnavailable(Exception): ...        # counts toward the 5-failures/60 s breaker
class FrontierRefused(Exception): ...            # stop_reason == "refusal" -> local draft or human


def _error_code(exc: anthropic.APIStatusError) -> str | None:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        details = (body.get("error") or {}).get("details") or {}
        return details.get("error_code")
    return None


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            max_retries=1,                                    # SDK default 2 (and it retries timeouts)
            timeout=httpx2.Timeout(9.0, connect=3.0),         # per attempt; the stage budget is enforced below
        )

    async def generate_structured(self, *, system: str, messages: list[dict], schema: type[BaseModel],
                                  temperature: float, max_tokens: int, timeout_s: float, request_id: str):
        del temperature  # 400 on Claude 4.7+ (incl. Sonnet 5) and removed from anthropic>=1.0 (TypeError)
        try:
            async with asyncio.timeout(timeout_s):           # §7.7 frontier stage: 20 s total, retries included
                resp = await self._client.messages.parse(
                    model=self._model, max_tokens=max_tokens, system=system, messages=messages,
                    output_format=schema, thinking={"type": "disabled"},
                )
        except TimeoutError as exc:
            raise FrontierUnavailable("deadline") from exc
        except anthropic.RateLimitError as exc:
            if _error_code(exc) == "enforced_spend_limit_reached":      # no retry-after; retries are futile
                raise FrontierBudgetExhausted("org monthly spend cap") from exc
            raise FrontierUnavailable("rate_limited") from exc
        except anthropic.BadRequestError as exc:
            if "usage limits" in str(exc):                              # own org/workspace spend limit (HTTP 400)
                raise FrontierBudgetExhausted("configured spend limit") from exc
            raise                                                       # programming error: surface, do not retry
        except (anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
            raise FrontierUnavailable(type(exc).__name__) from exc

        if resp.stop_reason == "refusal":
            raise FrontierRefused(getattr(resp.stop_details, "category", None))
        price_in, price_out = PRICES[self._model]
        cost = (Decimal(resp.usage.input_tokens) * price_in + Decimal(resp.usage.output_tokens) * price_out) / Decimal(1_000_000)
        # resp.stop_reason == "max_tokens" or resp.parsed_output is None -> hand raw text to the §6.6 repair path
        return resp.parsed_output, resp.usage, cost, resp._request_id
```

Notes on the snippet:
- The raw text still goes through the §6.6 validator. The API grammar does not enforce `maxLength` or `maxItems` (F3).
- If prompt caching is enabled later, add `cache_creation_input_tokens` and `cache_read_input_tokens` to the cost formula. Caching is off in v1: our stable prefix is below Sonnet 5's 1,024-token minimum, and traffic at demo volume is too sparse for 5-minute caches to matter.
- **Verify at build** (contract test with a mocked `httpx2` transport): that `messages.parse` accepts `thinking`, that `.body` has the documented error shape, and the exact message text of spend-limit 400s.

**D4 Budget and breaker (§7.5).**
- Before the call, compute the worst-case cost as `input_tokens_est × price_in + max_tokens × price_out`. The estimate comes from `count_tokens`, or from a conservative characters-per-token bound. Refuse the call if the worst case exceeds $0.05 or `frontier_spend_today + worst > FRONTIER_DAILY_BUDGET_USD`.
- After the call, book the actual cost from `usage` in Redis and in `llm_calls`.
- `FrontierBudgetExhausted` sets `frontier_enabled_runtime=false` until the next UTC day (own budget) or the next month (org cap). It raises an alert (`tw_frontier_budget_remaining_usd`) and is **not** counted as a breaker failure.
- `FrontierUnavailable` counts toward the 5-failures/60 s breaker (open for 120 s).
- Every failure falls back to a local draft or human escalation (§7.7).

**D5 Account setup (owner, one-time).**
1. Create the workspace `ticketward-demo`. The Default Workspace cannot carry limits.
2. Set the workspace **spend limit**, for example $35/month for a $1/day demo cap (§16 P11), with an alert at 50%. Set workspace **rate limits** well below the organization's, for example 30 RPM, 100k ITPM and 20k OTPM (a proposal).
3. Create a **workspace-scoped** API key and store it in the host secret store (§12.6). It never goes in `.env.example`.
4. Leave `default_inference_geo` at `global` unless L-03 requires US-only.
5. If any non-synthetic data is ever processed, request **ZDR** for the organization before enabling the frontier, and do not use Batch for that data.

**D6 Vendor-review checklist (L-03).** The admin records completion as `vendor_review_ack_at`.

| # | Item | Evidence / where | Status |
|---|---|---|---|
| 1 | Data-processing roles (processor) and DPA accepted | DPA 2025-02-24 (F7) | Available; owner reviews |
| 2 | Training on our data: prohibited | Commercial Terms (F7) | Confirmed in terms |
| 3 | Default retention of prompts and outputs | Privacy center "within 30 days" vs docs "not retained by default" (F6) | **Confirm with Anthropic in writing** |
| 4 | ZDR need and scope (Messages eligible; Batch, Console and Managed Agents not) | F6 | Decide: not needed for synthetic-only demo; required for real data |
| 5 | Flagged-content retention (up to 2 years, plus 7 years for classifier scores) | Privacy center | Accept or escalate |
| 6 | Subprocessors and objection process | trust.anthropic.com/subprocessors; 15-day window | Review list |
| 7 | International transfers (SCCs, UK, Swiss) and inference geography (global vs `us` at 1.1×) | DPA; data-residency docs | Decide geo |
| 8 | Security attestations (SOC 2 Type II, ISO 27001:2022, ISO 42001:2023) | Trust Center (NDA for reports) | Request reports |
| 9 | Breach notification ≤ 48 h | DPA | Confirmed in DPA |
| 10 | Acceptable Use Policy fit (support drafting) | https://www.anthropic.com/legal/aup | Owner reads |
| 11 | Output-use restrictions: the AUP prohibits using inputs or outputs "to train an AI model" without authorization, and the Commercial Terms bar "competing AI models" | AUP 2025-09-15; Commercial Terms | **Do not train on Claude outputs.** Claude is used for E6 evaluation and frontier drafts only (see `synthetic-data-generation.md`) |
| 12 | Spend controls in place (workspace limit, key scope, budget, breaker) | D4/D5 | Implement |
| 13 | Masking and residual-PII gate before egress; egress allow-list (`api.anthropic.com`) | §7.5 #6, §12.10 | Implement and test |
| 14 | Model lifecycle monitoring (retirement dates, ≥60-day notice) | Deprecations page | Quarterly check; alert on notice e-mail |
| 15 | Price change handling (L-15): dated price table in config | `providers/pricing.py` | Implement |

**D7 Batch API for E6 (evaluation only).** It is 50% cheaper (Sonnet 5 $1/$5), but **not ZDR-eligible (29-day retention)** and fast mode is not available on it. Use it only with synthetic data. **Do not use it to generate training data**: the AUP prohibits training models on Claude outputs (F7, SI-7). Results "arrive in any order", so key them by `custom_id`.

**D8 Model and cost table** (computed from the F1 prices; token counts are assumptions: typical 3,700 in and ≤600 out; worst 9,000 in):

| Model | Typical draft | Worst, 600 out | Worst, 2,000 out | Typical drafts per $2/day |
|---|---|---|---|---|
| **claude-sonnet-5** | **$0.0134** | $0.0240 | $0.0380 | ~149 |
| claude-opus-5-5 | $0.0268 | $0.0480 | **$0.0760 (over the $0.05 cap)** | ~75 |
| claude-haiku-4-5-20251001 | $0.0067 | $0.0120 | $0.0190 | ~299 |

These are **estimates**. The new tokenizer's ~30% growth and any thinking tokens must be measured in E6 with real `usage`.

---

## SPEC IMPACT (recorded; the spec was NOT edited)

| # | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §7.1 `LLMProvider.generate_structured(..., temperature, ...)`, §6.6 "Temperature is 0" | Claude 4.7+ models return 400 on non-default sampling parameters, and `anthropic` ≥1.0 removed them (TypeError). | The Anthropic adapter ignores `temperature`. Document that frontier outputs are not temperature-deterministic, and use recorded cassettes for evals. |
| SI-2 | §7.5 `max_tokens=600` | Sonnet 5 thinks by default, thinking counts toward `max_tokens`, and there is a ~30% tokenizer increase. | Send `thinking={"type":"disabled"}` and set `max_tokens=800`. Re-measure truncation in E6. |
| SI-3 | §7.5 "timeout 20 s; 1 retry" vs §7.7 "Frontier 20 s" | A 20 s timeout plus a retry exceeds the 20 s stage budget. SDK defaults are 10 min and 2 retries, and timeouts are retried. | Use a per-attempt timeout of about 9 s, `max_retries=1` and an outer `asyncio.timeout(20)`. |
| SI-4 | §7.5 budget/breaker | The spend cap returns 429 `enforced_spend_limit_reached` with no retry-after, and configured spend limits return 400. | Map both to "budget exhausted": open the breaker, do not retry, raise an alert. |
| SI-5 | §7.5 `FRONTIER_MODEL` | Verified lineup. Haiku 4.5's retirement floor is 2026-10-15. | Default to `claude-sonnet-5`, with a startup check against the Models API. |
| SI-6 | §12.6 "key scoped to its own workspace with a spend limit" | Confirmed feasible, but limits cannot be set on the Default Workspace. | Name the dedicated workspace and its limits (D5). |
| SI-7 | §9.1 item 2 ("Family A e.g. Anthropic Claude") and item 9 (generator ToS) | The Usage Policy (2025-09-15) prohibits "Utilization of inputs and outputs to train an AI model" without prior authorization. The Commercial Terms separately bar "competing AI models". | Do not use Claude as the train/val generator. Use the §9.1.9 fallback (open-weights), as `synthetic-data-generation.md` recommends. Claude stays for E6 and frontier drafts. |
| SI-8 | §9.8 M-10 / L-15 | Prices dated 2026-09-26. Sonnet 5 at $2/$10 is now standard. | Add the dated price table (D8) to `providers/pricing.py`. |
| SI-9 | §6.6 / §7.4 schemas | The API grammar ignores `maxLength`, `maxItems` and similar constraints (F3). | Keep strict server-side validation (already in §6.6). Do not treat constrained output as fully validated. |

---

## IMPLEMENTATION CHECKLIST

- [ ] Pin `anthropic==1.8.0` (with `httpx2` as a transitive dependency). If OTel `httpx` instrumentation must see SDK calls, call `httpx2.alias_httpx()` at startup before anything imports `httpx` (MIGRATION.md).
- [ ] `providers/anthropic.py` per D3. `providers/pricing.py` holds a dated price table. `providers/circuit.py` implements the breaker, with `FrontierBudgetExhausted` handled separately.
- [ ] Startup: validate `FRONTIER_MODEL` via `client.models.retrieve(...)`. Refuse `frontier_enabled=true` without `vendor_review_ack_at` (§7.5 #1).
- [ ] Contract tests with a mocked transport: spend-cap 429 body, workspace-limit 400, refusal, `max_tokens` truncation, timeout → fallback.
- [ ] E6 run (Batch, synthetic only): measure the token counts under the new tokenizer, the `stop_reason` distribution and the effort sweep. Update D8 with real numbers.
- [ ] Owner: carry out D5 in the Console and complete the D6 checklist. Ask Anthropic about item 3 (default retention).
- [ ] Metrics: `tw_llm_cost_usd_total{provider="anthropic"}`, `tw_frontier_budget_remaining_usd` and breaker state. Reconcile monthly against the Usage and Cost Admin API.

## OPEN RISKS / TO VERIFY

| Item | Status |
|---|---|
| The two retention statements disagree (30-day deletion vs "not retained by default") | **To confirm with Anthropic** (D6 #3) |
| `messages.parse` + `thinking` + `output_config` interplay, and the `.body` shape of spend-limit errors | **Verify** in contract tests |
| Actual tokens and cost per complex draft under the new tokenizer | Measure in E6 |
| Prices and models change (L-15). Haiku 4.5 has no deprecation notice as of 2026-09-26. With ≥60 days' notice, a notice issued today would mean retirement no earlier than about 2026-11-25. | Dated table plus quarterly review. Haiku is not used (D1). |
| Output-training restrictions (AUP plus Commercial Terms) for any use of Claude outputs as training data | Resolved by policy: no training on Claude outputs (SI-7). Owner confirms. |
| Cyber-safeguard refusals on security-adjacent tickets | Low: security intents are frontier-denylisted (§7.5 #2). Handle `refusal` gracefully anyway. |

## LINKED ADR

- **ADR-0015**: Anthropic adapter, gated. Record: `claude-sonnet-5` default; structured outputs via `messages.parse` (tool-less); thinking disabled; no sampling parameters; `max_tokens=800`; timeout, retry and deadline settings; spend-limit error semantics; dedicated workspace; vendor checklist reference.

## SOURCES (all accessed 2026-09-26)

1. Models overview: https://platform.claude.com/docs/en/about-claude/models/overview
2. Pricing: https://platform.claude.com/docs/en/about-claude/pricing
3. Model deprecations (status table, 60-day notice, parameter deprecations): https://platform.claude.com/docs/en/about-claude/model-deprecations
4. Claude Sonnet 5 overview and "What's new": https://platform.claude.com/docs/en/models/sonnet-5/overview ; https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5
5. Claude Opus 5.5 overview: https://platform.claude.com/docs/en/models/opus-5-5/overview
6. Thinking: https://platform.claude.com/docs/en/build-with-claude/thinking ; Effort: https://platform.claude.com/docs/en/build-with-claude/effort
7. Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
8. Prompt caching (minimums, isolation): https://platform.claude.com/docs/en/build-with-claude/prompt-caching
9. Rate limits and spend limits: https://platform.claude.com/docs/en/api/rate-limits
10. Workspaces: https://platform.claude.com/docs/en/manage-claude/workspaces
11. API and data retention (ZDR, feature eligibility, Covered Models): https://platform.claude.com/docs/en/manage-claude/api-and-data-retention
12. Data residency: https://platform.claude.com/docs/en/manage-claude/data-residency
13. Privacy center, commercial retention: https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data ; certifications: https://privacy.claude.com/en/articles/10015870-what-certifications-has-anthropic-obtained
14. Commercial Terms: https://www.anthropic.com/legal/commercial-terms ; DPA: https://www.anthropic.com/legal/data-processing-addendum ; Usage Policy (effective 2025-09-15; "Do Not Abuse our Platform"): https://www.anthropic.com/legal/aup ; Trust Center and subprocessors: https://trust.anthropic.com/ , https://trust.anthropic.com/subprocessors
15. Python SDK docs: https://platform.claude.com/docs/en/api/sdks/python ; repo and MIGRATION.md: https://github.com/anthropics/anthropic-sdk-python ; PyPI: https://pypi.org/pypi/anthropic/json
16. OSV (anthropic 1.8.0: none): https://api.osv.dev/v1/query

---

**Document Version**: 1.0
**Next Update**: After E6 measurements and the owner's vendor-review responses
