# PII Masking with Presidio - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Partially resolved. The current APIs, built-in recognizer coverage, defaults and gotchas are verified from source. Custom recognizers and the reversible-mapping logic are designed, and their regexes and logic are tested with the stdlib. The spaCy md-vs-lg latency and the 200-ticket fixture evaluation are pending (P4).
**Category**: Privacy / Security (OWASP LLM02 Sensitive Information Disclosure)
**Linked ADR(s)**: ADR-0019 (Presidio masking before every model, log and frontier call), ADR-0030 (app-level AES-GCM + crypto-shred)
**Spec sections**: §5.6 (placeholders), §7.2 step 1, §7.5 #6 (residual-PII gate ≥ 0.6), §7.7 (PII mask budget 1 s, fail closed), §7.8 (reveal toggle), §10 (`tickets`), §11 (`/tickets/{id}/reveal-pii`), §12.5, §12.10, §20 L-13, §23
**Method**: ERPROT §0. Presidio source code and configs (read from the repository's new home), official docs, spaCy model metadata, gitleaks rules. All accessed 2026-09-26.

---

## EXECUTIVE SUMMARY

1. **Versions and project home.** `presidio-analyzer` and `presidio-anonymizer` are at **2.2.364** (MIT, 2026-07-22, Python ≥3.10,<3.15). **The project has moved:** `github.com/microsoft/presidio` now returns HTTP 301 to **`github.com/data-privacy-stack/presidio`**, and the docs moved to `presidio.dataprivacystack.org` under the "Data Privacy Stack" banner. The PyPI names are unchanged. Update the links in ADR-0019 and pin exact versions with hashes (supply chain, R-12).
2. **Built-in coverage handles most of §12.5.**
   - Credit cards: pattern score 0.3, raised to 1.0 when the Luhn check passes and dropped when it fails.
   - IBAN, validated by checksum.
   - Email, phone (via `phonenumbers`; default regions US, GB, DE, FR, IL, IN, CA, BR), IP, URL and crypto wallets.
   - US SSN, passport, driver's license, ITIN and bank numbers.
   - spaCy NER for PERSON, NRP, LOCATION (GPE/LOC/FAC) and DATE_TIME. ORGANIZATION is ignored by default ("Has many false positives").
   - **There is no built-in recognizer for API keys, secrets or street addresses.** Custom recognizers are given below, with gitleaks-derived secret patterns.
3. **Several defaults would damage triage.** `DateRecognizer` and `UuidRecognizer` are **enabled by default**, and NER maps DATE/TIME to `DATE_TIME`. Left as is, they mask `charge_date`, `timestamp` and `workspace_id` entities (§5.6). LOCATION would mask "EU office" and lose the region. Pass an explicit `entities=[…]` list to `analyze()`.
4. **Four gotchas from the source.**
   - (a) `PatternRecognizer` defaults to `re.DOTALL | re.MULTILINE | re.IGNORECASE`. Case-sensitive secrets (`AKIA…`) must override this.
   - (b) The regex `allow_list` is joined with `|` and applied with **`search()`** to each detected span, so an unanchored allow term (`okta`) would *un-mask* a PERSON span such as "Okta Smith". **Anchor every allow-list regex with `^…$`.**
   - (c) The anonymizer processes spans **end-to-start**, so indexed placeholders (`<EMAIL_1>`) must be assigned in reading order before replacement.
   - (d) Since 2.2.361 the `hash` operator uses a random salt by default.
5. **spaCy models (3.8.0 metadata).** sm is 12 MB with NER F 0.843; **md is 31 MB with 0.847**; lg is 382 MB with 0.855; trf is 436 MB with 0.899. spaCy's published CPU speed is **10,014 WPS for lg vs 684 WPS for trf**. Recommendation: **default to `en_core_web_md`**, which is 351 MB smaller than lg for −0.8 NER-F points on OntoNotes. Switch to lg only if the fixture's PERSON recall is ≥ 2 points better. trf does not fit the 1 s budget on CPU. The md-vs-lg *speed* difference is **UNVERIFIED** and must be measured.
6. **Reversible mapping.**
   - Typed, indexed placeholders assigned in reading order and reused across the thread.
   - Customer-typed fake placeholders are escaped first.
   - **Card numbers keep only the last 4 digits** in the map.
   - The map is JSON encrypted with AES-256-GCM, with AAD binding it to ticket id, purpose and key id. It is stored with the ticket, never logged or sent to models, and revealed only through the audited endpoint.
   The logic is tested with the stdlib. One design consequence: `mask()` is intentionally *not* idempotent, so it runs exactly once on raw text. The residual-PII gate re-runs only the analyzer.

---

## QUESTIONS

| # | Question (spec §23 + implementer needs) | Answered in |
|---|---|---|
| Q1 | What do the built-in recognizers cover, and which custom recognizers are needed (`tm_live_…` keys, IBAN, Luhn cards)? | F2, F3, D2 |
| Q2 | What does spaCy model size cost in latency (lg vs md vs trf)? | F5, D1 |
| Q3 | What goes in the evaluation fixture, and what are its metrics? | D6 |
| Q4 | How is the reversible mapping designed and stored? | F4, D3 |
| Q5 | What are the current analyzer and anonymizer APIs, and how do allow-lists, the residual gate, performance and fail-closed behaviour work? | F1–F4, D1–D5 |

---

## FINDINGS

All links below were accessed 2026-09-26.

### F1. Versions and project governance

| Package | Version (PyPI) | Date | License | Python |
|---|---|---|---|---|
| presidio-analyzer | 2.2.364 | 2026-07-22 | MIT | >=3.10,<3.15 |
| presidio-anonymizer | 2.2.364 | 2026-07-22 | MIT | >=3.10,<3.15 |
| presidio-evaluator (research repo) | 0.3.2 | 2026-08-04 | MIT | — |
| spacy | 3.8.16 | 2026-08-24 | MIT | >=3.9,<3.15 |

- `https://github.com/microsoft/presidio` returns 301 → `https://github.com/data-privacy-stack/presidio`.
- `microsoft/presidio-research` returns 301 → `data-privacy-stack/presidio-research`.
- The docs redirect from `microsoft.github.io/presidio` to `presidio.dataprivacystack.org`, which identifies the project as a "Data Privacy Stack" initiative.
- OSV lists no vulnerabilities for presidio-analyzer 2.2.364.

### F2. Analyzer API (from `analyzer_engine.py`, `pattern_recognizer.py`, `recognizer_registry.py`)

- `AnalyzerEngine(registry=None, nlp_engine=None, app_tracer=None, log_decision_process=False, default_score_threshold=0, supported_languages=None, context_aware_enhancer=None)`. If no NLP engine is given, it builds the default one.
- `analyze(text, language, entities=None, correlation_id=None, score_threshold=None, return_decision_process=False, ad_hoc_recognizers=None, context=None, allow_list=None, allow_list_match="exact", regex_flags=re.DOTALL|re.MULTILINE|re.IGNORECASE, nlp_artifacts=None) -> list[RecognizerResult]`. The docstring says: "Unsupported entities are ignored with a logged warning … deprecated and will raise an error in a future version."
- `NlpEngineProvider(nlp_engines=None, conf_file=None, nlp_configuration=None).create_engine()`
- `RecognizerRegistry(recognizers=None, global_regex_flags=…IGNORECASE, supported_languages=None)`, with `.load_predefined_recognizers(languages, nlp_engine, countries)`, `.add_recognizer(r)`, `.remove_recognizer(name, language=None)` and `.add_recognizers_from_yaml(path)`.
- `PatternRecognizer(supported_entity, name=None, supported_language="en", patterns=None, deny_list=None, context=None, deny_list_score=1.0, global_regex_flags=re.DOTALL|re.MULTILINE|re.IGNORECASE, version="0.0.1", country_code=None)`.
- `Pattern(name, regex, score)`. Presidio compiles patterns with the third-party **`regex`** module, not `re`.
- `validate_result(text) -> bool | None`: True raises the score to `MAX_SCORE`, False drops it to `MIN_SCORE` (the result is discarded). `invalidate_result(text)`: True discards.
- Allow-list regex semantics, verbatim from the source: `pattern = "|".join(allow_list)` … `if not re_compiled.search(word, timeout=REGEX_TIMEOUT_SECONDS): new_results.append(result)`. Matching uses `search`, so it matches partially.

### F3. Default recognizers and NLP mapping (`conf/default_recognizers.yaml`, `conf/default.yaml`)

| Recognizer | Entity | Enabled by default | Ticketward decision |
|---|---|---|---|
| CreditCardRecognizer (Luhn `validate_result`, weak pattern 0.3, context words) | CREDIT_CARD | yes | **mask** (last-4 kept) |
| IbanRecognizer (checksum) | IBAN_CODE | yes | **mask** |
| EmailRecognizer | EMAIL_ADDRESS | yes | **mask** |
| PhoneRecognizer (`phonenumbers`; regions US, GB, DE, FR, IL, IN, CA, BR; score 0.4) | PHONE_NUMBER | yes | **mask**. Add apac regions (AU, SG, JP) and more EU regions, because accounts span us/eu/apac (§3). |
| IpRecognizer | IP_ADDRESS | yes | **mask** |
| UrlRecognizer | URL | yes | **mask** (reset links often carry tokens). KB links in drafts are handled by the URL allow-list, not here. |
| CryptoRecognizer | CRYPTO | yes | mask |
| UsSsn / UsPassport / UsLicense / UsItin / UsBank | US_* | yes | mask |
| NhsRecognizer | UK_NHS | yes | mask |
| MedicalLicenseRecognizer | MEDICAL_LICENSE | yes | leave out of `entities` (not relevant) |
| **DateRecognizer** | DATE_TIME | **yes** | **exclude**: it would destroy `charge_date` and `timestamp` (§5.6) |
| **UuidRecognizer** | UUID | **yes** | **exclude**: it would destroy `workspace_id` |
| MacAddressRecognizer | MAC_ADDRESS | yes | mask |
| spaCy NER PERSON / NORP→NRP | PERSON, NRP | via NLP | **mask** |
| spaCy NER GPE/LOC/FAC→LOCATION | LOCATION | via NLP | **exclude** (region signal). Mask street addresses with the custom recognizer instead (D2). |
| spaCy NER ORG | ORGANIZATION | **ignored** by default ("Has many false positives") | keep unmasked (B2B company names are business data) |

The default NLP config uses `en_core_web_lg`, with `labels_to_ignore: [ORGANIZATION, CARDINAL, EVENT, LANGUAGE, LAW, MONEY, ORDINAL, PERCENT, PRODUCT, QUANTITY, WORK_OF_ART]` and `low_confidence_score_multiplier: 0.4`.

### F4. Anonymizer API (from `anonymizer_engine.py`, `core/engine_base.py`, `operators/*`, [docs](https://presidio.dataprivacystack.org/anonymizer/))

- `AnonymizerEngine().anonymize(text, analyzer_results, operators=None, conflict_resolution=ConflictResolutionStrategy.MERGE_SIMILAR_OR_CONTAINED, merge_entities_with_spaces=True) -> EngineResult`.
- Operators: `replace` (`new_value`, default `<ENTITY_TYPE>`), `redact`, `hash` (`hash_type` sha256/sha512; **random salt by default since 2.2.361**, so pass `salt` for referential integrity), `mask` (`chars_to_mask`, `masking_char`, `from_end`), `encrypt` (`key`), `custom` (`lambda`), `keep` and `surrogate_ahds`. Deanonymize: `decrypt` through `DeanonymizeEngine`.
- Overlaps: "the PII with the higher score will be taken". When one span contains another, the larger wins.
- **Processing order:** `sorted(pii_entities, reverse=True)`, i.e. end → start. A stateful counter lambda therefore numbers the *last* email `_1`.
- The `custom` operator's `validate()` "intentionally do[es] NOT call the lambda" (to avoid side effects in stateful lambdas; issue #2024), and `operate()` raises if the lambda returns a non-`str`.
- Custom operators subclass `Operator` (`operate`, `validate`, `operator_name`, `operator_type`) and register with `engine.add_anonymizer(cls)`.

### F5. spaCy models (from spaCy's `meta/*-3.8.0.json` and [Facts & Figures](https://spacy.io/usage/facts-figures))

| Pipeline | Size | Vectors | NER P / R / F | Notes |
|---|---|---|---|---|
| en_core_web_sm 3.8.0 | 12 MB | none | 0.843 / 0.844 / 0.843 | |
| **en_core_web_md 3.8.0** | **31 MB** | 20,000 unique × 300 | 0.844 / 0.851 / **0.847** | recommended default |
| en_core_web_lg 3.8.0 | 382 MB | 342,918 unique × 300 | 0.852 / 0.859 / 0.855 | Presidio default |
| en_core_web_trf 3.8.0 | 436 MB | none (roberta-base) | 0.897 / 0.901 / 0.899 | GPU-oriented |

- All four are MIT-licensed and trained on OntoNotes 5, and all require spaCy `>=3.8.0,<3.9.0`.
- Speed (spaCy's benchmark, 10,000 Reddit comments, end to end): **en_core_web_lg 10,014 WPS on CPU (14,954 on GPU); en_core_web_trf 684 WPS on CPU (3,768 on GPU)**. No figure is published for md. md and lg share the architecture and differ mainly in the size of the vectors table, so similar speed is *expected* but **UNVERIFIED**.
- Budget check (§7.7, 1 s): a 20,000-character ticket is roughly 3,500–4,000 words. At lg-class speed that is about 0.35–0.4 s of NER on spaCy's benchmark hardware (**ANALYTICAL**), which is inside budget. trf would take about 5–6 s, which is outside it.

### F6. Secret patterns (from gitleaks' [config/gitleaks.toml](https://github.com/gitleaks/gitleaks/blob/master/config/gitleaks.toml))

These rules are reused as Presidio patterns:

| Rule id | Regex (verbatim) |
|---|---|
| aws-access-token | `\b((?:A3T[A-Z0-9]\|AKIA\|ASIA\|ABIA\|ACCA)[A-Z2-7]{16})\b` |
| github-pat | `ghp_[0-9a-zA-Z]{36}` |
| github-fine-grained-pat | `github_pat_\w{82}` |
| slack-bot-token | `xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*` |
| stripe-access-token | `\b((?:sk\|rk)_(?:test\|live\|prod)_[a-zA-Z0-9]{10,99})(?:[\x60'"\s;]\|\\[nr]\|$)` |
| jwt | `\b(ey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9\/\\_-]{17,}\.(?:[a-zA-Z0-9\/\\_-]{10,}={0,2})?)(?:[\x60'"\s;]\|\\[nr]\|$)` |
| private-key | `(?i)-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----[\s\S-]{64,}?KEY(?: BLOCK)?-----` |

The `tm_live_…` format is **fictional** (Taskmoor), so we define it ourselves (D2).

---

## DECISION / RECOMMENDATION

**D1 Engine configuration.** Use spaCy `en_core_web_md` by default, keep the lg switch behind a setting, and pass an explicit entity list.

```python
# backend/src/ticketward/pii/masker.py (engine setup)
import re

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer

from ticketward.pii.recognizers import custom_recognizers

MASK_ENTITIES = [
    "PERSON", "NRP", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "URL",
    "CRYPTO", "MAC_ADDRESS", "US_SSN", "US_PASSPORT", "US_DRIVER_LICENSE", "US_ITIN", "US_BANK_NUMBER",
    "UK_NHS", "TASKMOOR_API_KEY", "SECRET_TOKEN", "STREET_ADDRESS",
]   # deliberately NOT: DATE_TIME, UUID, LOCATION, ORGANIZATION, MEDICAL_LICENSE (see F3)

# Anchored (^...$) because Presidio applies allow-list regexes with search() to each detected span (F2).
ALLOW_LIST = [
    r"^acct_[A-Za-z0-9]{4,32}$",                 # account ids stay (§7.2)
    r"^<[A-Z][A-Z0-9_]*_\d+>$",                  # our own placeholders (residual scan)
    r"^(?:okta|azure ad|onelogin|google workspace|taskmoor|scim|saml|sso|gantt)$",
]


def build_analyzer(spacy_model: str = "en_core_web_md") -> AnalyzerEngine:
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": spacy_model}],
    }).create_engine()
    registry = RecognizerRegistry(supported_languages=["en"])
    registry.load_predefined_recognizers(languages=["en"], nlp_engine=nlp)
    registry.remove_recognizer("PhoneRecognizer")
    registry.add_recognizer(PhoneRecognizer(supported_regions=("US", "CA", "GB", "IE", "DE", "FR", "NL",
                                                               "ES", "IT", "IN", "AU", "SG", "JP", "BR", "IL")))
    for r in custom_recognizers():
        registry.add_recognizer(r)
    return AnalyzerEngine(registry=registry, nlp_engine=nlp, supported_languages=["en"])


def analyze(engine: AnalyzerEngine, text: str):
    return engine.analyze(text=text, language="en", entities=MASK_ENTITIES,
                          allow_list=ALLOW_LIST, allow_list_match="regex")
```

Verified in source (main, 2026-09-26): `PhoneRecognizer` is re-exported by `presidio_analyzer.predefined_recognizers.__init__` and takes `supported_regions` and `leniency`. Re-check against the pinned 2.2.364 wheel in a unit test. Load the engine **once per worker** at startup (model load takes seconds), and warm it up with one call.

**D2 Custom recognizers.** Every pattern below was run against a positive and a negative example with the stdlib `re`, with the same flags as below. For example, upper-case `TM_LIVE_…` must *not* match the case-sensitive key pattern. Presidio compiles with the `regex` module, which accepts this syntax. Re-run the tests under `regex` in CI.

```python
# backend/src/ticketward/pii/recognizers.py
import re

from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer

CASE_SENSITIVE = re.DOTALL | re.MULTILINE          # override Presidio's default IGNORECASE


def custom_recognizers() -> list[EntityRecognizer]:
    taskmoor_key = PatternRecognizer(
        supported_entity="TASKMOOR_API_KEY", name="TaskmoorApiKeyRecognizer",
        patterns=[Pattern("cd live/test key", r"\btm_(?:live|test)_[A-Za-z0-9]{24,64}\b", 0.95)],
        context=["key", "token", "api", "secret"], global_regex_flags=CASE_SENSITIVE,
    )
    secrets = PatternRecognizer(                     # gitleaks-derived (F6)
        supported_entity="SECRET_TOKEN", name="SecretTokenRecognizer", global_regex_flags=CASE_SENSITIVE,
        patterns=[
            Pattern("aws access key", r"\b(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16}\b", 0.9),
            Pattern("github pat", r"\bghp_[0-9a-zA-Z]{36}\b|\bgithub_pat_\w{82}\b", 0.95),
            Pattern("slack token", r"\bxox[baprse]-[0-9A-Za-z-]{10,}\b", 0.9),
            Pattern("stripe-style key", r"\b(?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99}\b", 0.9),
            Pattern("jwt", r"\bey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9/\\_-]{17,}\.[a-zA-Z0-9/\\_-]{10,}={0,2}", 0.9),
            Pattern("pem private key", r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY-----[\s\S]{64,}?-----END[ A-Z0-9_-]{0,100}PRIVATE KEY-----", 1.0),
        ],
    )
    street = PatternRecognizer(                       # heuristic, US/UK-style; evaluate on the fixture
        supported_entity="STREET_ADDRESS", name="StreetAddressRecognizer",
        patterns=[Pattern("number + street + suffix",
                          r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln"
                          r"|Drive|Dr|Court|Ct|Way|Place|Pl|Terrace)\b\.?", 0.5)],
        context=["address", "ship", "billing", "located", "office"],
    )
    return [taskmoor_key, secrets, street]
```

The built-in `CreditCardRecognizer` already implements Luhn in `validate_result`. This is verified from the source and matches our stdlib test: `4242 4242 4242 4242` is valid and the `…4241` variant is not. The built-in `IbanRecognizer` already validates the mod-97 checksum. Do **not** re-implement either one. Only extend context words if the fixture shows misses.

**D3 Placeholders and the reversible map.**
1. **Escape spoofed placeholders first.** Replace customer-typed `<TYPE_n>` with `‹TYPE_n›`. The replacement has the same length, so analyzer offsets stay valid. Without this, a ticket containing `<EMAIL_2>` could be de-masked into a real value.
2. **Resolve overlaps.** Higher score wins, then the longer span. Then **assign indexes in reading order**, per entity type, reusing an index for the same normalized value across the whole thread (lower-cased email, digits-only phone or card). Our own replacement loop avoids the anonymizer's end-to-start numbering. `AnonymizerEngine` with a pre-computed `custom` lambda is an acceptable alternative.
3. **Map contents:** `{"<EMAIL_1>": "dana@acme.example", "<CARD_LAST4_1>": "4242", …}`. **Never keep a full card number (PAN)** in the map (see SI-3 for the raw copy).
4. **Storage:** `pii_map_enc = AESGCM(key).encrypt(nonce_96bit, json_bytes, aad=f"{ticket_id}|pii_map|{key_id}".encode())`. Store `(key_id, nonce, ciphertext)` in the ticket row, using the same key management as `message_enc` (§12.2). It is crypto-shredded with the raw text after 90 days (§10).
5. **Use:** it is **never** sent to models, logs, traces or Langfuse. `POST /tickets/{id}/reveal-pii` decrypts it for authorized roles and writes audit `pii.reveal` (already in §11). Drafts keep their placeholders, and the UI de-masks them only for authorized viewers at approval time.
6. **`mask()` runs exactly once, on raw text.** It is not idempotent by design, because it escapes placeholders. The stdlib test covers reading-order numbering, value reuse across messages, overlap resolution, spoof escaping and PAN → last-4.

```python
# core of the tested logic (scratch test: reading order, thread reuse, spoof escaping, PAN->last4)
PLACEHOLDER_SPOOF_RE = re.compile(r"<([A-Z][A-Z0-9_]*_\d+)>")

def resolve_overlaps(spans):  # spans: presidio RecognizerResult-like (entity_type, start, end, score)
    kept = []
    for s in sorted(spans, key=lambda s: (-s.score, -(s.end - s.start), s.start)):
        if all(s.end <= k.start or s.start >= k.end for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s.start)   # reading order -> <EMAIL_1> is the first email
```

**D4 Residual-PII gate and log scrubbing.**
- Before any frontier call (§7.5 #6), and before persisting `message_masked`, re-run `analyze()` on the **masked** text. The placeholders are allow-listed by the anchored regex. **Any result with score ≥ 0.6 blocks the frontier call**, and above-threshold hits on persistence are counted (`tw_pii_residual_total`).
- The structlog scrubber (§12.10) reuses the email, phone, card, IBAN, key and secret regexes. It does not use NER, because NER is too slow per log line.

**D5 Latency and fail-closed behaviour.** Run `analyze` in a worker thread with a bounded limiter (§14.2), under `asyncio.timeout(1.0)` (§7.7). On timeout or any exception, fail closed: `human_escalation`, no model calls, and a reason recorded (spec). Measure P50/P95 for 2 KB, 8 KB and 20 KB tickets on the reference box, for md vs lg.

**D6 Evaluation fixture (200 tickets, P4).**

| Aspect | Design |
|---|---|
| Composition | 200 synthetic tickets. At least 60 contain emails, phones and cards in varied formats (`+44 20 …`, `(555) 010-…`, cards with spaces or dashes); 20 contain IBANs; 20 `tm_live_` keys; 15 other secrets (AWS, JWT, PEM); 30 person names, including lower-case and non-Western names; 15 street addresses. **Hard negatives:** `acct_` ids, UUID workspace ids, error codes, dates and amounts, product names (Okta, SCIM), and Luhn-invalid 16-digit order numbers. |
| Generation | Faker values via a seeded generator (`ml/datagen/pii_fixture.py`), plus 40 hand-written tricky cases. Gold spans are stored in presidio-evaluator's `InputSample` JSON (`presidio-evaluator` 0.3.2, MIT) so its evaluator can be reused. |
| Metrics | Per-entity span **recall** and precision, both strict and overlap. **Ticket-level leakage rate**: the share of tickets with at least one unmasked gold PII span (the number that matters for fail-closed). False-mask rate on the hard negatives. Latency P50/P95. |
| Targets | Spec: recall ≥ 0.95 for email, phone and card. Proposed additions: API keys and secrets ≥ 0.99; IBAN ≥ 0.95; PERSON ≥ 0.90; street address reported only; hard-negative false-mask ≤ 2%. |
| Gate | Fixture evaluation in CI (a unit-level fixture of 60 cases runs on every PR; the full 200 runs nightly). A drop of more than 2 points fails (§9.10 style). |

---

## SPEC IMPACT (recorded; the spec was NOT edited)

| # | Spec location | Finding | Suggested change |
|---|---|---|---|
| SI-1 | §12.5 "spaCy `en_core_web_lg`, verify size vs md" | md is 31 MB (NER F 0.847) vs lg at 382 MB (0.855). trf is too slow on CPU (684 vs 10,014 WPS for lg). | Default to md. Switch to lg only on measured fixture recall. Record the choice in ADR-0019. |
| SI-2 | §12.5 recognizer list, §5.6 entities | Presidio enables DATE_TIME and UUID by default, and NER LOCATION would mask regions. That conflicts with extracting `charge_date`, `timestamp`, `workspace_id` and `region`. There is no built-in address recognizer. | Specify the explicit `MASK_ENTITIES` list, a custom STREET_ADDRESS recognizer, and cities and countries left unmasked (document the residual risk in L-13). |
| SI-3 | §10 `tickets.message_enc` (raw text kept 90 days) | A pasted full card number stays in the encrypted raw copy, so the system stores PANs, which is relevant to PCI scope. **Verify against PCI DSS Req. 3** before any real deployment. | Replace PAN digits in the stored raw copy with last-4 at ingestion (the raw text is for audit, not payment processing). |
| SI-4 | §10 `tickets` columns | "Reversible mapping stored only encrypted with the ticket" (§12.5), but the table has no column for it. | Add `pii_map_enc bytea` and `pii_map_key_id text`, crypto-shredded with `message_enc`. |
| SI-5 | ADR-0019 / links | Presidio moved to the `data-privacy-stack` org, with new docs. | Update the links and record the governance change in the supply-chain review (R-12). |

---

## IMPLEMENTATION CHECKLIST

- [ ] Pin `presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364` and `spacy==3.8.x`. Install the `en_core_web_md-3.8.0` wheel from the spaCy models GitHub release **by URL plus sha256** in `uv.lock`, not with `spacy download` at runtime.
- [ ] `pii/recognizers.py` (D2) and `pii/masker.py` (D1/D3). The `PIIMasker.mask()` return type is `MaskResult(masked_text, map_enc, counts, residual_hits)`.
- [ ] Tests: the D3 stdlib cases ported to pytest; hypothesis property "no gold email or phone substring survives masking"; allow-list anchoring (a PERSON span "Okta Smith" must be masked); a case-sensitivity test for AKIA keys; DATE, UUID and `acct_` preserved.
- [ ] Startup and CI assertion: `set(MASK_ENTITIES) <= set(analyzer.get_supported_entities("en"))`. Presidio currently *ignores* unknown entity names with only a deprecation warning (F2), so a typo would silently disable masking of that type.
- [ ] AES-GCM map envelope with AAD. Rotation follows the `key_id` scheme. Crypto-shred through the retention job.
- [ ] Residual-PII gate before frontier calls, and a metric.
- [ ] Budget: `asyncio.timeout(1.0)` plus a bounded thread. Fail-closed path tested (T-PII-timeout → human_escalation).
- [ ] Build the fixture (D6) and add the CI gates. Benchmark md vs lg latency and recall, and record the result in ADR-0019.

## OPEN RISKS / TO VERIFY

| Item | Status |
|---|---|
| md vs lg CPU latency and PERSON recall on our fixture | **UNVERIFIED**; measure in P4 |
| Street-address regex recall (heuristic, US/UK formats only) | Reported only; the data is synthetic, and L-13 documents the residual risk |
| Lower-case or unusual person names missed by spaCy NER | Known NER limitation. Fixture measures it. Optional GLiNER recognizer later (`gliner` 0.2.29, Apache-2.0; Presidio ships `GLiNERRecognizer`) |
| PCI DSS implications of raw-text PAN storage | **To verify** (SI-3). Synthetic data only in the demo. |
| Presidio governance move | Monitor releases and maintainers. Pin hashes. |
| `phonenumbers` false positives on long numeric ids | Fixture hard negatives. Tune `leniency` if needed. |

## LINKED ADR

- **ADR-0019**: Presidio 2.2.364, spaCy md, explicit entity list, custom recognizers, anchored allow-list, own placeholder assignment, fixture gates. New repo links.
- **ADR-0030**: add the PII-map envelope (AES-256-GCM, AAD) and PAN last-4 handling.

## SOURCES (all accessed 2026-09-26)

1. Presidio repository (new home) and sources read: `presidio-analyzer/presidio_analyzer/{analyzer_engine.py, pattern.py, pattern_recognizer.py, recognizer_registry/recognizer_registry.py, nlp_engine/nlp_engine_provider.py, predefined_recognizers/generic/{credit_card,iban,phone}_recognizer.py, conf/default.yaml, conf/default_recognizers.yaml}` and `presidio-anonymizer/presidio_anonymizer/{anonymizer_engine.py, core/engine_base.py, operators/operator.py, operators/custom.py}`: https://github.com/data-privacy-stack/presidio (redirect from https://github.com/microsoft/presidio)
2. Presidio anonymizer docs: https://presidio.dataprivacystack.org/anonymizer/
3. PyPI: https://pypi.org/pypi/presidio-analyzer/json ; https://pypi.org/pypi/presidio-anonymizer/json ; https://pypi.org/pypi/presidio-evaluator/json ; https://pypi.org/pypi/spacy/json
4. presidio-research (evaluator): https://github.com/data-privacy-stack/presidio-research
5. spaCy model metadata: https://raw.githubusercontent.com/explosion/spacy-models/master/meta/en_core_web_{sm,md,lg,trf}-3.8.0.json ; speed: https://spacy.io/usage/facts-figures
6. gitleaks rules: https://github.com/gitleaks/gitleaks/blob/master/config/gitleaks.toml
7. OSV: https://api.osv.dev/v1/query (presidio-analyzer 2.2.364: none)

---

**Document Version**: 1.0
**Next Update**: After the P4 fixture evaluation and md/lg benchmark (fill in numbers and flip Status to Resolved)
