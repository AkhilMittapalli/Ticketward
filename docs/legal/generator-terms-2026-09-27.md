# Generator & Host Terms Snapshot — 2026-09-27

> **Engineering research notes, not legal advice.** This is a working snapshot of publicly posted
> vendor terms, prepared by an engineer for a portfolio ML project, so the team can make an informed,
> conservative choice of API host. It is not a legal opinion, was not prepared or reviewed by a lawyer,
> and must not be treated as one. Terms change; re-verify before every generation run (see
> `docs/legal/README.md`).

**Scope.** Ticketward's synthetic-data plan (`docs/research/synthetic-data-generation.md`) uses:
- **Family A** (train/val, ~4,050 records): `openai/gpt-oss-120b` (Apache-2.0), via a hosted inference API.
- **Family B** (test set, ~1,045 records): `mistralai/Mistral-Large-3-675B-Instruct-2512` (Apache-2.0), via Mistral's own API or another host.

The model license question (Apache-2.0 for both) was already resolved in `synthetic-data-generation.md`
F2 and is not repeated here. **This document covers the *host's* contract** — the terms you accept by
using their API — which is a separate legal layer on top of the model license. It replaces and extends
the `docs/legal/generator-terms-2026-09-26.md` reference named in that document's checklist (which was
never actually written) and resolves the "other hosts' terms for gpt-oss" and "Mistral pricing page"
items logged there as UNVERIFIED.

**Verdict question asked of every vendor:** *does anything in this host's terms forbid using API
outputs as fine-tuning data for an open-source-licensed small model published on Hugging Face (not a
model that competes with the host's own inference business)?* This is engineering judgment applying
plain-language contract terms, not a legal conclusion.

**Headline finding:** across all twelve hosts checked, none has a clause that forbids this use case.
Every "competing use" clause found is scoped to competing with *the host's own inference platform or
foundation models* (e.g., Groq, Together, DeepInfra's own service; Google's own Gemini family) — a small
non-competing triage classifier does not fall inside any of them. The one host-side clause anywhere
in this research that talks about *output-based training restrictions* at all is Mistral's, and it is
scoped to image outputs only. Everything else is silence (which is not a blocked verdict, just an
unaddressed one) or an explicit permission.

**Methodology (reproducible).** For each URL below, the page was fetched on 2026-09-27 with:
```
curl -sL --max-time 30 -A "Mozilla/5.0 ... Chrome/128.0.0.0 Safari/537.36" -o <vendor>.html <url>
sha256sum <vendor>.html
```
The raw HTML was saved only in a local scratch directory (not in this repo) and hashed as-is — the hash
is a byte-level fingerprint of the fetched page, not of a canonicalized text extraction, so it will also
change on cosmetic markup edits, not only on substantive text changes. For pages whose pricing/legal
text is injected client-side by JavaScript (noted per-vendor below), the raw-HTML hash mostly fingerprints
the page shell and is a weaker change-detection signal; those are flagged. Facts and quotes below were
then verified against the same saved, tag-stripped text (not accepted as-is from any AI summarization
tool), by grepping for the exact clause. Quotes are verbatim, ≤ 15 words, one per vendor.

---

## Family A candidates — `openai/gpt-oss-120b` hosts

### Groq

| | |
|---|---|
| Availability / model id | Confirmed. `openai/gpt-oss-120b`, 131,072 context. |
| Price (accessed 2026-09-27) | **$0.15 / $0.60** per 1M input/output tokens. Source: `console.groq.com/docs/models`. |
| Batch API / discount | Yes — Batch API, **50% off** standard rate, JSONL up to 50,000 lines / 200 MB, 24h–7-day turnaround. Available on Developer and Enterprise tiers (`console.groq.com/docs/batch`, via search of Groq's own docs — not independently re-fetched). |
| Free tier | Yes, a free tier exists. |
| Rate limits, new/free account, gpt-oss-120b | **Inconsistent across Groq's own pages** — `docs/rate-limits` reports 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD for free-tier accounts; `docs/models` reports 1,000 RPM / 250,000 TPM for "Developer Plan." These cannot both be the free-tier number for the same model — **UNVERIFIED, check the console at sign-up.** |
| OpenAI-compatible base URL | `https://api.groq.com/openai/v1` (`console.groq.com/docs/openai`). |
| Policy pages, accessed 2026-09-27 | Services Agreement: `https://console.groq.com/docs/legal/services-agreement` (Last Modified: June 22, 2026). Data policy: `https://console.groq.com/docs/your-data`. |
| SHA-256 | services-agreement: `d19931b4ae886a51e1b4ba178807729d0e7e1e6dc5b37537af2443baa34598c3`; your-data: `6b660ebd78725a4584a2d8a854b40a1470f0f070d3c2092cf52ddc3feab1e699` |
| Key clauses | Customer owns Inputs/Outputs (§8.1). By default Groq does not access/use/store/retain Inputs or Outputs beyond what's needed to run the service; abuse/reliability logs kept ≤ 30 days unless a customer enables Zero Data Retention. §6.3(e) bars using the service to build a product that competes with Groq's *Cloud Services* — an inference platform, not a downstream triage model. |
| Quote (≤ 15 words) | "Groq is not permitted to use Inputs or Outputs for training" |
| Verdict | **Allowed.** Contractually the strongest "no training on your data" language of any host checked. |
| Open questions | Reconcile the two conflicting rate-limit figures above before relying on the free tier for volume; confirm whether Batch API needs a paid Developer-tier upgrade first. |

### Together AI

| | |
|---|---|
| Availability / model id | Confirmed. `openai/gpt-oss-120b`. |
| Price (accessed 2026-09-27) | **$0.15 / $0.60** per 1M tokens. Source: `together.ai/models/gpt-oss-120b`. |
| Batch API / discount | Yes — Batch Inference, **50% off** most serverless chat models, 24h window, up to 30B tokens/job (`together.ai/blog/batch-api`, Together's own site). |
| Free tier | Not confirmed on the pages fetched — **UNVERIFIED**. |
| Rate limits, new account | Not confirmed on the pages fetched — **UNVERIFIED**. |
| OpenAI-compatible base URL | `https://api.together.xyz/v1` (Together's own OpenAI-compatibility docs). |
| Policy page, accessed 2026-09-27 | `https://www.together.ai/terms-of-service` ("Updated May 19, 2026"). |
| SHA-256 | `9273f4e74e045d0c7be58be3fde37393c0e98535831227b9764eb1eb61622e78` |
| Key clauses | Customer "exclusively owns" Output. **Training is opt-out, not opt-in**: the account's Privacy & Security setting must be switched to "No" (store prompts / allow training → No) to enable Zero Data Retention; only under ZDR does Together commit not to use "data and outputs" for model training. Left at the default, Together may store and train on your data. §(c) bars using the service "to develop a product or service that is competitive with the Company's products or services" — again, an inference-platform non-compete, not a bar on downstream fine-tuning. |
| Quote (≤ 15 words) | "your data and outputs are not stored, retained, or used for model training" |
| Verdict | **Allowed, conditional** — enable Zero Data Retention in account settings *before* generating, otherwise Together's own default is training-permissive on your prompts. |
| Open questions | Confirm current ZDR toggle state in the account console immediately before the run; free-tier terms and rate limits unconfirmed. |

### Fireworks AI

| | |
|---|---|
| Availability / model id | Confirmed. `accounts/fireworks/models/gpt-oss-120b`. |
| Price (accessed 2026-09-27) | **$0.15 / $0.60** per 1M tokens (serverless). Source: `fireworks.ai/models/fireworks/gpt-oss-120b`. |
| Batch API / discount | Fireworks documents Standard/Priority/Fast *serverless* tiers, not a distinct discounted batch tier — **UNVERIFIED** whether an async/batch discount exists. |
| Free tier | Yes — **$1 free starter credit** (`fireworks.ai/pricing`). |
| Rate limits, new account | Per Fireworks' own account-quotas docs (via search, not independently re-fetched): **10 RPM** account-wide with no payment method on file; adding a card unlocks spend tiers up to 6,000 RPM (Tier 1 $50/mo → Tier 4 $50,000/mo). |
| OpenAI-compatible base URL | `https://api.fireworks.ai/inference/v1` (must be exact, no trailing slash; model id needs the full `accounts/fireworks/models/...` prefix). |
| Policy pages, accessed 2026-09-27 | Terms of Service: `https://fireworks.ai/terms-of-service` (redirects to a Sanity-CDN-hosted PDF, "Last updated: July 10, 2026" per search; **the fetched PDF was not machine-readable text** — see note). Privacy Policy: `https://fireworks.ai/privacy-policy` ("Last Modified: 8/11/2026"). |
| SHA-256 | Privacy policy (HTML): `ce5cba5a33222f47a15866906458b16be69d8f00c973fc9c8613c9436e0e572a`. ToS PDF also fetched (binary, not text-verifiable) — see Sources. |
| Key clauses | Privacy Notice §1: no training on prompts/API inputs without opt-in, and no logging of prompt/generation data for open models without opt-in. A Data Processing Addendum (`fireworks.ai/dpa`) is incorporated into the ToS. |
| Quote (≤ 15 words) | "We do not use your prompts, training data, or API inputs to train" |
| Verdict | **Allowed.** Safe-by-default (no opt-in needed to avoid Fireworks training on your data). |
| Open questions | The ToS PDF could not be parsed as text in this session — its clauses were not independently verified beyond the search-summarized quotes above; re-fetch as HTML or re-check manually. Batch/async discount existence unconfirmed. |

### DeepInfra

| | |
|---|---|
| Availability / model id | Confirmed. `openai/gpt-oss-120b` (also `-Turbo` and `-Ultra` variants at different price/quality points). |
| Price (accessed 2026-09-27) | **$0.037 / $0.17** per 1M tokens (standard variant). Cross-checked against OpenRouter's endpoint listing for the DeepInfra route, which independently reports the same $0.037/$0.17. Source: `deepinfra.com/openai/gpt-oss-120b`. **This is the cheapest of all hosts checked.** |
| Batch API / discount | Not found on the pages fetched — **UNVERIFIED**. |
| Free tier | Not confirmed — **UNVERIFIED**. Rate limiting is by concurrency, not a token quota: 200 concurrent requests per account (raisable on request), per DeepInfra's own rate-limits docs (via search). |
| OpenAI-compatible base URL | `https://api.deepinfra.com/v1/openai`. |
| Policy page, accessed 2026-09-27 | `https://deepinfra.com/terms` ("Last modified: August 17th, 2026"). |
| SHA-256 | `799313a7b7f7db4f2e8705c327f057cbe5569378659638acc988807886febb88` |
| Key clauses | Customer retains IP rights in Customer Data. §7: "Zero Data Retention" is the *default*, not opt-in — DeepInfra deletes submitted/generated data as soon as the request is served, with narrow carve-outs (e.g., customer-requested retention, or when routing to Google/Anthropic models, whose own training policy then applies — irrelevant for gpt-oss). §11(a)(i) bars using the service in a way "competitive with any business of Provider" — again an inference-platform non-compete. |
| Quote (≤ 15 words) | "will not use Customer Data to train, fine-tune, or otherwise improve any model" |
| Verdict | **Allowed.** Safe-by-default, cheapest, no opt-in required. |
| Open questions | Confirm whether a batch/async discount exists; confirm free-trial credit (if any) before assuming one. |

### Cerebras

| | |
|---|---|
| Availability / model id | Confirmed. `gpt-oss-120b`, ~3,000 tok/s (fastest of the hosts checked). |
| Price (accessed 2026-09-27) | **$0.35 / $0.75** per 1M tokens — the highest per-token price of the pure-play hosts checked, traded for much higher throughput. Corroborated independently by OpenRouter's endpoint listing ($0.00000035/$0.00000075) and a search-engine summary of `cerebras.ai/pricing`; **the pricing page itself is JavaScript-rendered and did not yield readable text on direct fetch**, so treat the exact figure as well-corroborated but not independently re-verified byte-for-byte. |
| Batch API / discount | Not found — **UNVERIFIED**. |
| Free tier | Yes, exists, but its exact numbers conflict across sources found: one Cerebras support page reports 5 RPM / 30,000 uncached + 90,000 total TPM per model; a separate community source claims "1M tokens/day, 1 request/second." **UNVERIFIED — reconcile at sign-up.** The paid Developer (PayGo) tier for gpt-oss-120b specifically is reported at 1,000 RPM / 500,000 TPM. |
| OpenAI-compatible base URL | `https://api.cerebras.ai/v1`. |
| Policy pages, accessed 2026-09-27 | Two documents exist and it is unclear which governs API/inference use: (a) `https://cloud.cerebras.ai/terms` — **this page is a JavaScript single-page app; the fetched HTML contained no readable terms text** (14 characters of visible text after stripping markup — a shell, not the contract). (b) `https://www.cerebras.ai/terms-of-service` ("Effective August 27, 2024" — notably not updated in about two years), which by its own scope clause covers "the training-as-a-service product and the inference-as-a-service product, each as accessed through the APIs." A third document, a Cerebras Inference EULA PDF linked from search results, was not fetched in this pass. |
| SHA-256 | cloud.cerebras.ai/terms (shell, low information value): `524c113c08e3e02c354ec9498168ec7dfe4ef99cde0ec4ccd3838cd8b0a7b1c2`; www.cerebras.ai/terms-of-service: `95c51b661d5e2ee2be0d07b67c1ac66a27fb2af40febae035f0a0f08f5853902` |
| Key clauses | From the www.cerebras.ai document: Cerebras may use "Service Content" to provide the service, comply with law, and enforce the terms, but "the foregoing does not grant Cerebras the right to use Service Content for the purpose of training or fine-tuning models." |
| Quote (≤ 15 words) | "the right to use Service Content for the purpose of training or fine-tuning models" |
| Verdict | **Likely allowed**, but confidence is lower than other hosts because (a) the actual governing contract for API/inference use is ambiguous among three candidate documents, and (b) the one document with readable text is dated 2024. |
| Open questions | Identify which of the three candidate documents is the operative inference-API contract; re-fetch `cloud.cerebras.ai/terms` with a JS-capable tool; reconcile the free-tier rate-limit conflict; confirm no batch API. |

### Baseten

| | |
|---|---|
| Availability / model id | Confirmed. `gpt-oss-120b`, listed as serverless "Model APIs" (an on-demand endpoint) as well as a "dedicated" H100 deployment option. |
| Price (accessed 2026-09-27) | **$0.10 / $0.50** per 1M tokens for the serverless Model API. Source: `baseten.co/library/gpt-oss-120b/`. |
| Batch API / discount | Not found for the serverless catalog — **UNVERIFIED**. Dedicated deployment is priced by GPU-time, not tokens, and is a different cost model entirely. |
| Free tier | Yes — new accounts receive sign-up credits, exact amount not stated on the pages fetched. Pay-as-you-go, no minimum monthly spend on the Basic plan. |
| Rate limits, new account | Not found — **UNVERIFIED**. |
| OpenAI-compatible base URL | `https://inference.baseten.co/v1` (serverless Model APIs catalog only; dedicated deployments use a different per-model URL). |
| Policy page, accessed 2026-09-27 | `https://www.baseten.co/terms-and-conditions/` ("Last updated September 15, 2026"). |
| SHA-256 | `00b944d3a7930d7a926128d882e33ddbee349add46e8ba1fdc32cc550beb4b46` |
| Key clauses | §6.3, titled "No Training on Customer Content": Baseten will not use Customer Content — including "Customer Models, Model Outputs, or inference logs" — to train, fine-tune, or develop ML/AI models. §4.3(e) bars using the service "to build a competing product or service" (Baseten's own platform). |
| Quote (≤ 15 words) | "to train, fine-tune, or otherwise develop machine learning or artificial intelligence models" |
| Verdict | **Allowed.** Explicit, unconditional, no opt-in needed. |
| Open questions | Confirm sign-up credit amount and any rate limits before relying on the free tier for the pilot. |

### OpenRouter (routing layer over the above)

| | |
|---|---|
| Availability / model id | Confirmed, `openai/gpt-oss-120b` (append `:provider`, e.g. `:cerebras`, to pin a route). Aggregates ~20 upstream providers. |
| Price (accessed 2026-09-27) | Ranges by upstream route, from the platform's own endpoints API: AkashML / CoreWeave $0.03/$0.17 (cheapest listed) up to Cerebras $0.35/$0.75 (priciest). DeepInfra, Together, Groq all appear as routes at their own native prices (see rows above). Source: `openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints` (JSON, fetched directly). |
| Batch API / discount | Not applicable — OpenRouter is a synchronous pass-through router, not a batch processor. |
| Free tier | A rate-limited free variant appears in OpenRouter's own site navigation as `openai/gpt-oss-120b:free`; its limits were not independently confirmed in this pass — **UNVERIFIED**, treat as pilot-only, not for bulk generation. |
| Rate limits | Vendor-dependent; OpenRouter itself does not publish a separate universal quota beyond the routed provider's own limits. |
| OpenAI-compatible base URL | `https://openrouter.ai/api/v1`. |
| Policy pages, accessed 2026-09-27 | Terms: `https://openrouter.ai/terms` ("Last Updated: August 31, 2026"). Privacy: `https://openrouter.ai/privacy` ("Last Updated: August 31, 2026"). |
| SHA-256 | terms: `78bd904d6a429ec860e428a5b25fabbe3f8959de0504c66da790a737416ce657`; privacy: `cca903030163a55ebabf05013b2f4e9d63aabb91f33e48667a58806c4e44f6dd` |
| Key clauses | §6.1: "Your ownership rights in the Output are set forth in the Model Terms for each Model" — i.e., OpenRouter defers output ownership and use rights to whichever upstream provider you route to. §6.1 also states OpenRouter itself "has opted out of model training with the Models it uses" (its own privacy policy: "OpenRouter does not use your Inputs or Outputs for model training"), but the *upstream* Model Provider may still train unless that specific provider is excluded (an account-level toggle exists to disallow routing to training providers). |
| Quote (≤ 15 words) | "OpenRouter does not use your Inputs or Outputs for model training" |
| Verdict | **N/A / depends on the pinned upstream route.** OpenRouter itself imposes no extra restriction, but the verdict for any specific generation run is really the verdict of whichever provider you routed to that day, unless you pin the route and disable training-permissive providers in account settings. |
| Open questions | If used, pin the exact upstream provider (`:together`, `:deepinfra`, etc.) rather than "auto," and enable the "don't route to training providers" account toggle, so the effective terms match the specific host row above rather than whatever OpenRouter picks at request time. |

### Hugging Face Inference Providers (routing layer)

| | |
|---|---|
| Availability / model id | Confirmed. `openai/gpt-oss-120b:<provider>` (e.g. `:cerebras`, `:fireworks-ai`) via `huggingface.co/docs/inference-providers/guides/gpt-oss`. Same routing-layer pattern as OpenRouter, over a smaller partner list. |
| Price (accessed 2026-09-27) | Billed per the underlying provider's compute cost with "no markup from Hugging Face" per HF's own pricing docs; effectively the same as that provider's own row above. |
| Batch API / discount | Follows the underlying provider; not a separate HF feature. |
| Free tier | Free accounts get **$0.10/month** in Inference Providers credits; PRO ($9/mo) gets **$2.00/month**; Enterprise gets $2/seat. Source: `huggingface.co/docs/inference-providers/guides/gpt-oss` and `huggingface.co/docs/inference-providers/pricing` (via search). |
| Rate limits | Not found specifically — **UNVERIFIED**; presumably gated by the monthly credit amount rather than RPM/TPM. |
| OpenAI-compatible base URL | `https://router.huggingface.co/v1` (confirmed directly from HF's own guide, including working code samples). |
| Policy pages, accessed 2026-09-27 | ToS: `https://huggingface.co/terms-of-service` (states "Effective Date: September 15, 2022" — old; does not appear to have been revised for Inference Providers specifically and defers data practices to the Privacy Policy). Privacy: `https://huggingface.co/privacy` ("Effective Date: March 28, 2023" — also old). |
| SHA-256 | ToS: `0f00ca90746820e21c80c4d40866fa6595a47c68c3460bc44e057db3cff4522a`; Privacy: `18efbea58e1577c6aea11c7eee5bc9ba86ac538fcb9a7d5d63d7ada008d7c98d` |
| Key clauses | Neither document fetched addresses, in terms specific enough to quote, whether HF or its Inference Providers train on data routed through the service. The ToS names "Inference Providers" as a defined service category but points to the Privacy Policy for data handling; the Privacy Policy in turn does not appear to have been updated to describe Inference Providers-specific practices in the version fetched. No restriction on the customer's own downstream use of outputs was found either way. |
| Quote (≤ 15 words) | *(none — no clause found specific enough to quote without misrepresenting it)* |
| Verdict | **Depends on the pinned upstream provider**, same reasoning as OpenRouter. Not itself a source of restriction, but also not a source of an explicit "we don't train" commitment the way Groq/DeepInfra/Baseten/Fireworks are directly. |
| Open questions | HF's general ToS/Privacy Policy dates (2022/2023) predate Inference Providers as a product; look for a dedicated Inference Providers data-practices page before relying on this route for anything beyond quick pilots. |

---

## Family A — hyperscaler options (checked for completeness; not the primary recommendation)

### Amazon Bedrock

| | |
|---|---|
| Availability / model id | Confirmed GA. `openai.gpt-oss-120b-1:0` (bedrock-runtime, Chat Completions) or `openai.gpt-oss-120b` (bedrock-mantle, Responses API). Also available via Bedrock Custom Model Import and in AWS GovCloud. |
| Price (accessed 2026-09-27) | Four tiers, from `aws.amazon.com/bedrock/pricing/`: **Standard** $0.15/$0.60, **Priority** $0.2704/$1.0815, **Flex** $0.0773/$0.3090, **Batch** $0.0773/$0.3090 per 1M tokens (Flex/Batch = 50% of Standard). |
| Batch / discount | Yes, a dedicated Batch tier at 50% off Standard (table above). |
| Free tier | General AWS free-tier promos exist account-wide; nothing gpt-oss-specific found. |
| Rate limits, new account | Not found specifically for gpt-oss-120b — **UNVERIFIED**. |
| OpenAI-compatible endpoint | Not the standard pattern — Bedrock normally uses AWS SigV4-signed SDK calls; an OpenAI-style "bedrock-mantle" surface was referenced in AWS's own docs for the Responses API but its base URL was not independently confirmed in this pass — **UNVERIFIED**. |
| Policy pages, accessed 2026-09-27 | `https://aws.amazon.com/legal/bedrock/third-party-models/` (consolidated per-vendor terms page) and the model card `https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-oss-120b.html`. |
| SHA-256 | third-party-models page: `464fb7da47578d7c29a2b9ddcaf5485f0926243dc9458461c666908e1dda2cde`; gpt-oss-120b model card: `fd37a948bb764399f9e4e4c3ea0fb9584b2e5d996f4f1907142e6935471680a2` |
| Key clauses — **important nuance found** | The consolidated terms page states plainly: **"OpenAI openweight serverless models on Amazon Bedrock are sold by AWS"** (as opposed to OpenAI's own proprietary hosted models — GPT-5 etc. — which are "sold by OpenAI" and carry a separate "OpenAI Services Agreement" with a clause barring use of Output "to develop artificial intelligence models that compete with OpenAI's products and services"). **That competing-model clause does not apply to gpt-oss-120b** because it is explicitly carved out as "sold by AWS," not "sold by OpenAI," on this same page. The gpt-oss-120b model-card page itself adds no further restriction beyond a link to the model's own license/usage-policy (Apache-2.0 + OpenAI's two-sentence USAGE_POLICY, already covered in `synthetic-data-generation.md`). AWS's own general Bedrock commitment (from its public FAQ/blog, not independently re-fetched as primary text in this pass) is that inputs/outputs are not shared with model providers and are not used to train Bedrock's own or third-party foundation models. |
| Quote (≤ 15 words) | "OpenAI openweight serverless models on Amazon Bedrock are sold by AWS" |
| Verdict | **Allowed.** This is a genuine finding worth flagging to the owner: a careless read of the Bedrock terms page could wrongly apply OpenAI's competing-model restriction to gpt-oss-120b; it does not apply here. |
| Open questions | AWS's "does not train on customer content" commitment for Bedrock generally was found via secondary (AWS blog/FAQ) sources, not re-verified as primary contract text in this pass; requires an AWS account with billing enabled, which is a heavier sign-up than the pure-play hosts. |

### Azure AI Foundry

| | |
|---|---|
| Availability / model id | Confirmed GA. `gpt-oss-120B` in the Foundry Model Catalog, single-H100-capable, deployable from Hub-based or serverless Foundry projects. |
| Price (accessed 2026-09-27) | **UNVERIFIED.** The catalog page links out to `aka.ms/oai/pricing`, which returned HTTP 404 on direct fetch in this pass, and the general Azure OpenAI pricing page's visible content did not list a gpt-oss-120b row. Do not assume parity with Bedrock/Groq pricing without checking the Foundry portal directly at sign-up. |
| Batch / discount | Yes — "Global Batch" deployment type, **50% discount** vs. Global Standard pricing for completions returned within 24 hours (Microsoft Learn, via search). |
| Free tier | General Azure free-trial credit exists account-wide; nothing gpt-oss-specific confirmed. |
| Rate limits, new account | Not found — **UNVERIFIED**. |
| OpenAI-compatible endpoint | Azure AI Foundry / Azure OpenAI historically uses its own resource-scoped endpoint + api-version query parameter pattern rather than a single shared OpenAI-style base URL — **not a simple base-URL swap**; confirm the exact resource endpoint format in the Foundry portal at deployment time. |
| Policy page, accessed 2026-09-27 | `https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy` (page metadata: `ms.date: 2026-05-18`; most recent change-log entry "3 October 2025"). |
| SHA-256 | `df5ef70f63b925f0485fd893f255854ddf20942fb1c535538930c5309a2593c4` |
| Key clauses | Explicit and strong: prompts, completions, embeddings and training data "are NOT used by providers of Models sold by Azure to improve their models or services," "are NOT used to train any generative AI foundation models without your permission or instruction," and are not shared with OpenAI or other model providers. **"The models are stateless: no prompts or completions are stored in the model."** Fine-tuning data you upload is likewise not used to train any generative AI foundation model without your permission. |
| Quote (≤ 15 words) | "are NOT used to train any generative AI foundation models without your permission" |
| Verdict | **Allowed** on the terms checked, but the exact price is unverified, which matters for a $15 budget — confirm cost before committing to this host. |
| Open questions | Get the actual per-token price from the Foundry portal or an Azure sales/pricing calculator before use; confirm resource-endpoint URL format; requires an Azure subscription with billing, a heavier sign-up than the pure-play hosts. |

### Google Vertex AI (Model Garden, Model-as-a-Service)

| | |
|---|---|
| Availability / model id | Confirmed GA. `openai/gpt-oss-120b` as a MaaS "Open Model API" in Vertex AI Model Garden / Gemini Enterprise Agent Platform (Google's rename of Vertex AI Platform), regions `global` and `us-central1`. |
| Price (accessed 2026-09-27) | **UNVERIFIED.** The dedicated MaaS docs page for this model did not surface a price in the fetched excerpt, and the general Vertex AI pricing page exceeded this session's fetch size limit (~10 MB). Do not assume a figure without checking the Vertex console/pricing calculator directly. |
| Batch / discount | Not found in this pass — **UNVERIFIED** (Vertex AI does generally support batch prediction with a discount for its own models; not confirmed for this MaaS partner model specifically). |
| Free tier | Google Cloud's general new-customer credit exists account-wide; nothing gpt-oss-specific confirmed. |
| Rate limits, new account | Not found — **UNVERIFIED**. |
| OpenAI-compatible endpoint | Vertex AI MaaS models are normally called through Google's own Vertex endpoint/SDK conventions, not a drop-in OpenAI base URL — **UNVERIFIED** whether an OpenAI-compatible shim exists for this model. |
| Policy pages, accessed 2026-09-27 | `https://cloud.google.com/terms/service-terms` ("Last modified September 24, 2026" per the page's own version history). |
| SHA-256 | `0275c1ca8468fdad20cc3a32d06882f01c0e552ced08fd05d1061eb046dc4a48` |
| Key clauses — **read carefully** | §18 "Training Restriction": "Google will not use Customer Data to train or fine-tune any AI/ML models without Customer's prior permission or instruction." §17.a "Competitive Use": customers may not use an AI/ML Service or its Generated Output "to develop a similar or competing product or service" — **but this restriction explicitly does not apply to the Gemini Enterprise Agent Platform (formerly Vertex AI Platform) "so long as Customer does not use a Google Pre-Trained Model."** gpt-oss-120b is OpenAI's model, not a "Google Pre-Trained Model," so this carve-out should cover it. §17.b "Model Restrictions" separately bars using AI/ML output to "substitute, replace, or circumvent the use of a Google Model" or "create or improve models similar to a Google Model" — again scoped to *Google's own* models (Gemini etc.), not to a small triage classifier trained on an OpenAI-origin model's outputs. |
| Quote (≤ 15 words) | "Google will not use Customer Data to train or fine-tune any AI/ML models" |
| Verdict | **Likely allowed**, resting on the reading that gpt-oss-120b is not a "Google Pre-Trained Model" and our SLM is not "similar to" Gemini. This is a plain-language reading of real clauses, not a legal opinion — worth a second read given it's the one place in this research where a "competing product" and "model restriction" clause exists in the same breath as the model we'd be calling. |
| Open questions | Confirm price before use (unverified); confirm the §17.a/§17.b carve-outs really do cover a third-party open-weight MaaS model the way this reading assumes; confirm OpenAI-compatibility surface if any. |

---

## Family B — Mistral La Plateforme

| | |
|---|---|
| Availability / model id | Confirmed. **`mistral-large-3-25-12`** — this closes the "UNVERIFIED: confirm on mistral.ai" item from `synthetic-data-generation.md`'s Open Risks table. Source: `docs.mistral.ai/getting-started/models/` (model list) and `docs.mistral.ai/inference/pricing` (pricing table, same id). |
| Price (accessed 2026-09-27) | **$0.50 / $1.50** per 1M input/output tokens — confirmed directly on Mistral's own pricing docs, matching the OpenRouter-derived figure the background research had flagged as needing confirmation. Cached input: **$0.05** per 1M tokens (90% off). |
| Batch API / discount | Yes — **50% off** for batch/high-volume processing, per `mistral.ai/pricing/` ("Batch processing, for high-volume work, reduces the price by 50%"); exact batch-tier numbers per model were not separately itemized in the fetched excerpt but 50% off $0.50/$1.50 implies roughly $0.25/$0.75. |
| Free tier | Mistral's Free plan includes **$10/month** in API credits (`mistral.ai/pricing/`). |
| Rate limits, new account | Not found in the pages fetched — **UNVERIFIED**. |
| OpenAI-compatible base URL | `https://api.mistral.ai/v1` (Mistral's Chat Completions API is OpenAI-wire-compatible; swap base URL, key, and model name). |
| Policy pages, accessed 2026-09-27 | Commercial Terms of Service: `https://legal.mistral.ai/terms/commercial-terms-of-service` ("Effective: September 25, 2026" — two days before this snapshot). Pricing: `https://mistral.ai/pricing/`. Pricing docs: `https://docs.mistral.ai/inference/pricing`. |
| SHA-256 | Commercial terms: `69e568ea3c941cd49efc00ad0bb96f70511948020335f7d9f2ffb991a4739ed3`; pricing page: `623082c9ad261f0c20219c9b237e760a81d390af42188a9021bdc455720913cd`; pricing docs: `c4ec1dd83d49f709df815f5ff4cae94ce872d2dc0c99a7f01f2c953e445dd5fe` |
| Key clauses | §3.1: customer retains ownership of Customer Data and "owns all Output"; Mistral assigns its own rights in Output to the customer. §4.2 "Training": Mistral **will not** train its own models on Customer Data/Outputs **except** (a) an opt-out-by-default product where the customer opted in, (b) an opt-in-by-default product the customer didn't opt out of, (c) an Order Form says otherwise, or (d) the customer used **Labs or Preview Models** (identified by a `labs` prefix in AI Studio) — those train regardless of any opt-out. §3.3 "Output Restrictions": the *only* restriction on the customer's own downstream use of Output is "Customer may not use **image** Outputs to develop or train any image generation product that competes with a Mistral AI Product" — no equivalent restriction exists for text output, which is all Family B uses. |
| Quote (≤ 15 words) | "Customer may not use image Outputs to develop or train any image generation product" |
| Verdict | **Allowed.** Text-output fine-tuning is unrestricted; the only output-training restriction in the whole document is image-specific and inapplicable here. |
| Open questions | Confirm `mistral-large-3-25-12` is *not* tagged as a `labs`/Preview model in the account console (which would force training-on regardless of preference) before running Family B at volume; confirm current opt-in/opt-out toggle state for La Plateforme in account settings; a separate, narrower Mistral AI Privacy Policy / DPA (`legal.mistral.ai/terms/data-processing-addendum`, `chat.mistral.ai/legal/privacy-policy`) exists alongside the Commercial Terms and was not independently re-fetched in this pass — it governs personal-data handling, not the Output-training question, so it is lower priority but still open. |

---

## Addendum 2026-09-27 (owner decision D-07): Family B = DeepSeek-V3.2 on DeepInfra

DeepInfra does not host Mistral Large 3 (its Mistral catalog ends at Mistral Small 3.2 24B). The owner therefore chose `deepseek-ai/DeepSeek-V3.2` on DeepInfra for the test set, so one DeepInfra account and key serve both families. The Mistral La Plateforme section above stays as the documented, config-only alternative.

| Item | Finding (accessed 2026-09-27) |
|---|---|
| Model and license | `deepseek-ai/DeepSeek-V3.2`, 685B parameters. The repository `LICENSE` file is the **MIT License**, which places no restriction on using outputs, commercially or otherwise, and requires no attribution for outputs. |
| Host | DeepInfra: the same account, key, terms and defaults as Family A above (no training on customer data; zero retention by default). OpenAI-compatible base URL `https://api.deepinfra.com/v1/openai`, model id `deepseek-ai/DeepSeek-V3.2`. |
| Price (rendered on the model page) | **$0.26** / 1M input, **$0.38** / 1M output, **$0.13** / 1M cached input |
| Serving precision | **fp4**, as shown on the model page; recorded per record as `generator_quantization` |
| Context / JSON | 163,840 tokens; JSON `response_format` supported (per the model page) |
| Family independence | Differs from Family A (OpenAI gpt-oss) and from the base-SLM candidates (Qwen), so the train/test generator split and the no-home-field rule hold. It is never Claude. |
| Verdict | **Allowed** for "use outputs as test data for evaluating an open-source-licensed small model" (and training would also be allowed under MIT; test outputs are never used for training here). |
| Estimated cost | about $1.8 for test_synth at the rendered prices (the `generate --dry-run` estimate is authoritative) |

Hashes (raw fetched bytes, same method as above):

| Page | SHA-256 | Bytes |
|---|---|---|
| https://deepinfra.com/deepseek-ai/DeepSeek-V3.2 | `39d16581f1649baf84cdb66f4320e1166b9ba73b7d03215b0145d5cd301495cf` | 483,231 |
| https://huggingface.co/deepseek-ai/DeepSeek-V3.2 | `83ff576ab05b7ddc2aed4686e1773f6256e9a789053773e30456f5e0fe884af0` | 431,105 |
| https://huggingface.co/deepseek-ai/DeepSeek-V3.2/raw/main/LICENSE | `f2c6c602815669d292889e5be8c802f2ed950653b77999b1584e8e6aed25d040` | 1,084 |

The model-page hashes fingerprint dynamic HTML, so they are expected to change often; the LICENSE hash is the stable one to re-check before each run.

## Pricing summary (all dated 2026-09-27)

| Host | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| DeepInfra | 0.037 | 0.17 | Cheapest; safe-by-default terms |
| Baseten | 0.10 | 0.50 | Safe-by-default terms |
| Groq | 0.15 | 0.60 | Strongest contractual "no training" language; Batch −50% |
| Together AI | 0.15 | 0.60 | Training opt-out required (ZDR); Batch −50% |
| Fireworks AI | 0.15 | 0.60 | Safe-by-default; $1 free credit |
| AWS Bedrock (Standard) | 0.15 | 0.60 | Batch/Flex tier 0.0773/0.3090 (−50%) |
| Cerebras | 0.35 | 0.75 | ~4× faster tokens/sec; terms confidence lower |
| Azure AI Foundry | UNVERIFIED | UNVERIFIED | Terms strong; price not found |
| Google Vertex AI (MaaS) | UNVERIFIED | UNVERIFIED | Terms likely fine; price not found; one clause needs a careful read |
| OpenRouter | 0.03–0.35 | 0.17–0.75 | Pass-through of the above, by route |
| HF Inference Providers | = routed host | = routed host | "No markup"; small monthly credit |
| **Mistral Large 3** (Family B) | **0.50** | **1.50** | Batch ≈ −50%; cached input 0.05 |

---

## Recommendation (engineering judgment, not fact)

**Family A primary: DeepInfra.** Cheapest confirmed price ($0.037/$0.17), and its terms are safe by
default — no account setting needs to be remembered or flipped, unlike Together. **Family A fallback:
Groq** — same "safe by default" property, clearest and most explicit contractual "not permitted to
train on your data" language of any host checked, a documented Batch API, and clearly published (if
internally inconsistent) rate limits. Together AI remains usable as a second fallback but only if
Zero Data Retention is actively enabled first.

**Family B: Mistral Large 3 via La Plateforme directly**, as the existing research already concluded —
now with the price and model id independently confirmed from Mistral's own docs rather than inferred
from OpenRouter.

**Cost estimate**, reusing the call/token assumptions already in `synthetic-data-generation.md` F8
(5,265 Family-A calls at ~1,800 in / ~750 out tokens each; 1,080 Family-B two-stage calls at ~2,300 in /
~850 out tokens each — both **UNVERIFIED estimates pending the 50+50 pilot**, not new information from
this pass):

| Scenario | Family A | Family B | Total | Budget headroom ($15) |
|---|---|---|---|---|
| Primary (DeepInfra + Mistral standard) | 9.477M×$0.037 + 3.949M×$0.17 = **$1.02** | 2.484M×$0.50 + 0.918M×$1.50 = **$2.62** | **$3.64** | $11.36 |
| Fallback (Groq + Mistral standard) | 9.477M×$0.15 + 3.949M×$0.60 = **$3.79** | **$2.62** | **$6.41** | $8.59 |
| Fallback A, Mistral batch (−50%) | $3.79 | **$1.31** | $5.10 | $9.90 |

All scenarios leave comfortable headroom in the $15 budget for the mandatory 50+50 pilot, prompt
iteration, and regeneration after label QA (`synthetic-data-generation.md` D4). The $1.02 DeepInfra
figure matches that document's own "low host" placeholder exactly, and the $3.79/$2.62 figures match
its existing headline numbers exactly — this pass is a confirmation and citation upgrade of numbers
that were already directionally right, not a change to the plan.

**No host researched is blocked.** The closest things to a caveat are (a) Together AI's default
(non-ZDR) posture, which is training-permissive until you flip a switch, and (b) Google Vertex AI's
AI/ML competitive-use and model-restriction clauses, which plain-language reading says do not reach a
third-party open-weight model or a small non-competing triage classifier, but which sit close enough to
the topic to deserve a careful second read if Vertex is ever used instead of a pure-play host.

---

## Master UNVERIFIED / open-questions list (owner action items before sign-up or before the run)

1. Groq: reconcile the conflicting free-tier rate-limit figures (30 RPM/8,000 TPM vs. 1,000 RPM/250,000 TPM) in the console before relying on the free tier for volume.
2. Together AI: confirm Zero Data Retention is switched on in account settings before generating.
3. Fireworks AI: the Terms of Service PDF was not machine-readable in this pass; its clauses rest on a secondary (search-engine) summary, not this session's own verified text — re-check manually. Confirm whether a batch/async discount exists.
4. DeepInfra: confirm whether a batch API exists; confirm any free-trial credit.
5. Cerebras: identify which of three candidate documents (`cloud.cerebras.ai/terms` SPA, `www.cerebras.ai/terms-of-service` dated 2024, or the linked Inference EULA PDF) actually governs API/inference use; reconcile conflicting free-tier rate-limit reports; confirm no batch API.
6. Baseten: confirm sign-up credit amount and rate limits.
7. OpenRouter / HF Inference Providers: if used, pin the exact upstream provider and confirm that provider's own row in this document applies, rather than trusting the aggregator's default routing.
8. Amazon Bedrock: the "AWS does not train on customer content" claim rests on AWS's public FAQ/blog, not on this session's own fetch of primary contract text — re-verify; confirm OpenAI-compatible ("bedrock-mantle") endpoint details if that surface is used.
9. Azure AI Foundry: get the actual gpt-oss-120b per-token price from the Foundry portal (`aka.ms/oai/pricing` 404'd in this pass); confirm the exact resource-endpoint URL pattern.
10. Google Vertex AI: get the actual gpt-oss-120b MaaS price (page too large to fetch whole in this pass); double-check the §17.a/§17.b carve-out reading with a second pass before relying on Vertex for bulk generation.
11. Mistral: confirm `mistral-large-3-25-12` is not flagged `labs`/Preview in the console; confirm current opt-in/opt-out training toggle for the account; the separate Privacy Policy/DPA governing personal data was not independently re-fetched.
12. All hosts: re-verify every URL, date, and hash in this document immediately before the actual generation run, not just before the pilot — see `docs/legal/README.md`.

---

## Sources (all accessed 2026-09-27 unless noted; SHA-256 over the raw fetched HTML)

**Groq** — `console.groq.com/docs/legal/services-agreement`; `console.groq.com/docs/your-data`; `console.groq.com/docs/models`; `console.groq.com/docs/rate-limits`; `console.groq.com/docs/openai`; `console.groq.com/docs/batch` (via search, not independently fetched).
**Together AI** — `together.ai/terms-of-service`; `together.ai/models/gpt-oss-120b`; `docs.together.ai/docs/openai-api-compatibility` (via search); `together.ai/blog/batch-api` (via search).
**Fireworks AI** — `fireworks.ai/terms-of-service` (PDF, not text-verified); `fireworks.ai/privacy-policy`; `fireworks.ai/models/fireworks/gpt-oss-120b`; `fireworks.ai/pricing`; `docs.fireworks.ai/guides/quotas_usage/account-quotas` (via search).
**DeepInfra** — `deepinfra.com/terms`; `deepinfra.com/openai/gpt-oss-120b`; `docs.deepinfra.com/account/rate-limits` (via search).
**Cerebras** — `cloud.cerebras.ai/terms`; `www.cerebras.ai/terms-of-service`; `cerebras.ai/pricing` (readable text not obtained directly); `inference-docs.cerebras.ai/support/rate-limits` and `support.cerebras.net` FAQ (via search).
**Baseten** — `baseten.co/terms-and-conditions/`; `baseten.co/library/gpt-oss-120b/`; `baseten.co/pricing/`.
**OpenRouter** — `openrouter.ai/terms`; `openrouter.ai/privacy`; `openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints` (JSON).
**Hugging Face** — `huggingface.co/terms-of-service`; `huggingface.co/privacy`; `huggingface.co/docs/inference-providers/guides/gpt-oss`; `huggingface.co/docs/inference-providers/pricing` (via search).
**Amazon Bedrock** — `aws.amazon.com/legal/bedrock/third-party-models/`; `docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-oss-120b.html`; `aws.amazon.com/bedrock/pricing/`.
**Azure AI Foundry** — `ai.azure.com/catalog/models/gpt-oss-120B`; `learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy`; `azure.microsoft.com/en-us/pricing/details/azure-openai/`.
**Google Vertex AI** — `docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/openai/gpt-oss-120b`; `cloud.google.com/terms/service-terms`.
**Mistral AI** — `legal.mistral.ai/terms/commercial-terms-of-service`; `mistral.ai/pricing/`; `docs.mistral.ai/inference/pricing`; `docs.mistral.ai/getting-started/models/`.

**Full SHA-256 manifest** (vendor, url, HTTP status, bytes, sha256) is retained in this session's
scratch directory as `manifest.csv`, not committed to the repository, consistent with "do not store
full copies of terms in the repo." Anyone re-running this snapshot should regenerate it fresh rather
than trust a stale copy.
