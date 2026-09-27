# docs/legal

Engineering research notes, not legal advice. This folder holds dated **snapshots of third-party
vendor terms** for the APIs Ticketward calls — currently, the hosts used to generate synthetic
training/test data (see `docs/research/synthetic-data-generation.md` for the generator-family decision
itself: which models, which prompt families, why Anthropic/Claude is excluded from training data).

It does not hold full copies of anyone's terms of service. Each snapshot paraphrases the clauses that
matter for this project, quotes at most one short (<15 words) excerpt per vendor, and records a
SHA-256 hash of the fetched page so a later re-check can tell whether the page has changed since —
without us needing to store the page itself in the repository.

## What's here

| File | Contents |
|---|---|
| `generator-terms-YYYY-MM-DD.md` | A dated terms snapshot: per-vendor policy URLs, access date, SHA-256 of the fetched page, paraphrased key clauses + one quote, an allowed/blocked verdict for "use outputs as fine-tuning data for an open-source-licensed small model," and open questions. One file per snapshot pass — old dated files are kept, not overwritten, so you can diff what changed. |

The current snapshot is `generator-terms-2026-09-27.md`.

## When to refresh the snapshot

Vendor terms, pricing, and rate limits change without much notice, and this project trains on the
outputs — so treat the snapshot as perishable, not a one-time check:

1. **Before every generation run** (pilot or full), not just once at project start. Re-fetch each
   vendor's policy pages, recompute the SHA-256, and compare it to the previous snapshot's hash for
   that same URL. If a hash changed, re-read that page's clauses before proceeding — don't assume a
   changed hash is cosmetic.
2. **Before switching hosts or models** (e.g., moving off the primary host to the fallback, or adding a
   new candidate host).
3. **On the cadence implied by `synthetic-data-generation.md`'s checklist**: at P1 (pilot) start, and
   again before publishing any dataset built from a given run.
4. **Whenever a host's pricing or rate limits materially affect the cost arithmetic** in the research
   doc — re-run the numbers, don't just re-read the terms.

Write a new dated file rather than editing the latest one in place, so the history of what changed and
when stays intact. Reference the new file's date (`terms_snapshot_id`) in the data provenance fields
described in `synthetic-data-generation.md` D2, so every generated record can be traced back to the
terms snapshot that was current when it was created.

## How a snapshot is produced (so it's reproducible)

Each vendor page is fetched with a plain HTTP GET (e.g. `curl -sL <url> -o page.html`), saved only to a
local scratch location (never committed here), and hashed with a one-line command
(`sha256sum page.html`, or PowerShell `Get-FileHash page.html -Algorithm SHA256`). Facts and quotes are
taken from that same fetched text, not from a search engine's paraphrase of it, wherever the page's
content allowed it — some vendor pages render their text client-side via JavaScript and don't yield
readable text to a plain fetch; those are flagged individually in the snapshot rather than silently
skipped.

## Ground rules for anyone adding to this folder

- Never invent a price, model id, limit, or clause. Anything that can't be confirmed from the vendor's
  own page is marked **UNVERIFIED**, not guessed.
- Distinguish facts (what a page says) from recommendations (which host to use). A snapshot can and
  should say which vendors it recommends, but must not blur that into a claim about what the vendor's
  terms say.
- This is engineering judgment applying plain-language contract terms, not a legal opinion. If a real
  decision hinges on a specific clause, get an actual lawyer to read the primary document — don't rely
  on the paraphrase here.
- Read-only research: don't create vendor accounts, sign up for trials, or submit any forms while
  producing a snapshot.
