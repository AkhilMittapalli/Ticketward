# Public Sanitized Demo Deployment (single VM) - Expert Research Document

<!-- published-by: scripts/sync_research.py -->
> **Published research note.** Copied from the owner's working research log by
> `scripts/sync_research.py`. Section references (§) point to the project's private
> specification, which is not part of this repository.

**Created**: 2026-09-26
**Last Updated**: 2026-09-27
**Status**: Partially resolved. Hosting options have dated prices, and TLS, demo-mode, abuse, reset, backup and budget designs are all defined. Three decisions are still open:
- the final host SKU. Owner decision D-06 schedules this for P9, after the CPU latency benchmark (ADR-0026);
- whether to put Cloudflare in front at launch;
- the domain.

**Category**: Deployment / Operations
**Linked ADR(s)**: ADR-0026 (Docker Compose + Caddy; single-VM public demo); related ADR-0020 (auth), ADR-0024 (observability), ADR-0027 (ASVS), ADR-0015 (frontier budget)
**Spec sections**: §12.6 (secrets), §12.9 (container hardening), §14.5 step 11 (deploy), §15 (SLOs, backup/restore, runbooks), §16 P9/P11, §19 DoD-12/13, §21 R-09/R-11, §23

---

## EXECUTIVE SUMMARY

- **Host.** The recommended host is a **Hetzner Cloud CPX42**: 8 shared AMD vCPU, 16 GB RAM, 320 GB NVMe, in NBG1 or HEL1. It costs **€69.49/month + €0.50 IPv4** ($81.99 + $0.60), per Hetzner's live price feed accessed 2026-09-26. VAT treatment is assumed net, as on Hetzner's storage pages; **UNVERIFIED for cloud servers**.
  - The same-size **CX43** is listed at **€15.99** but was marked "not available" at access time, and Hetzner pitches that line at low CPU usage. Take it only if it is back in stock *and* passes the P9 triage-latency benchmark.
  - **DigitalOcean Basic 8 vCPU/16 GiB ($96/mo)** is the fallback, with CPU-Optimized ($168/mo) if shared CPU misses the latency SLO.
  - **Rejected:**
    - **Fly.io**: shared vCPUs have a 6.25% baseline with burst credits, so sustained CPU inference throttles; performance-8x is about $248 per 30 days; Compose `volumes:` are ignored and data lands on an ephemeral overlay.
    - **Oracle Always Free**: now **2 OCPU / 12 GB** for Always Free tenancies (1,500 OCPU-h + 9,000 GB-h per month), which is below target, with capacity and idle-reclamation risk.
- **TLS.** Caddy 2.11.x automatic HTTPS: Let's Encrypt with ZeroSSL fallback, the HTTP-01 and TLS-ALPN-01 challenges on by default, and an HTTP→HTTPS redirect. It needs the DNS record pointed at the VM, ports 80/443 reachable, and a persistent data directory. Use the staging CA while testing. If Cloudflare proxies the site, switch to DNS-01 (Caddy build with a Cloudflare DNS module) and set Cloudflare to "Full (strict)".
- **Demo mode.** `TW_DEMO_MODE=true` puts together:
  - immutable shared role accounts via a `demo-login` endpoint (or published credentials), with no password change and no per-account lockout for demo users;
  - admin and dangerous mutations disabled;
  - workflow writes limited by quotas;
  - frontier off, or $1/day plus an Anthropic workspace spend limit;
  - a banner, tighter input caps and 4-hour sessions;
  - no public Grafana/Tempo/Swagger.
- **Abuse protection** is layered:
  1. (Optional) Cloudflare Free: proxy, 1 rate-limit rule per IP per 10 s, and Turnstile on demo-login.
  2. Caddy: 1 MB bodies, GET/HEAD only to Next.js, internal paths return 404, client IP propagated.
  3. The app: `limits` sliding-window counters per IP and per user, daily global caps, queue-depth backpressure (429), `max_jobs=2`, timeouts, frontier budget and circuit breaker.
  4. Nightly reset.
- **Nightly reset** at 03:00 UTC is a systemd timer that runs the following steps. It also purges visitor-entered content.
  1. Turn maintenance on.
  2. Drain the worker.
  3. `pg_restore` the golden dump.
  4. Flush Redis (every session dies).
  5. Warm the demo tickets.
  6. Run the smoke test.
  7. Turn maintenance off.
- **Backups.** Use restic 0.19.1, which encrypts client-side, to Backblaze B2 ($6.95/TB-month, first 10 GB free) or Cloudflare R2 ($0.015/GB-month, 10 GB-month free, no egress fees), keeping 14 daily and 4 weekly copies. Run the restore drill monthly. **Take the demo backup after the reset** so visitor data isn't retained (spec impact SI-D2).
- **Budget.** About **$83-113/month** plus domain and VAT: VM about $82.6, backups $0 within free tiers, frontier $0-30.4. Details in D8.

---

## QUESTIONS

1. Which host for an 8 vCPU / 16 GB CPU VM, and at what dated cost? What about Hetzner, DigitalOcean, Fly.io and the Oracle free ARM tier?
2. How do we get TLS with Caddy auto-HTTPS, with and without Cloudflare in front?
3. Which demo-mode controls make a public, shared, write-capable demo safe?
4. Abuse protection: which rate limits, where, and should Cloudflare sit in front?
5. How do we reset nightly, and how does that interact with backups?
6. What is the monthly budget?
7. Where do backups go, and how are they encrypted, retained and drilled?

---

## FINDINGS

### F1. Host options (prices as published; accessed 2026-09-26)

| Option | vCPU / RAM / disk | CPU class | Published price (monthly) | Status at access | Fit |
|---|---|---|---|---|---|
| **Hetzner CX43** (Cost-Optimized) | 8 / 16 GB / 160 GB NVMe | shared Intel/AMD | **€15.99 / $18.49** (plan page lists NBG1, HEL1) | **"not available"** | Cheapest; Hetzner positions this line for low CPU usage |
| Hetzner CAX31 (Cost-Optimized, Arm) | 8 / 16 GB / 160 GB | shared Ampere | €20.99 / $24.99 | "not available" | Needs arm64 images for every service |
| **Hetzner CPX42** (Regular Performance) | 8 / 16 GB / 320 GB | shared AMD | **€69.49 / $81.99** (plan page lists NBG1, HEL1); SIN1 €93.49 / $109.99 | available | **Recommended** |
| Hetzner CPX41 (US: HIL1, ASH1) | 8 / 16 GB / 240 GB | shared AMD | €120.49 / $141.49 | available | US region, expensive |
| Hetzner CCX23 (General Purpose) | 4 dedicated / 16 GB / 160 GB | dedicated AMD | €85.99 / $101.49 (EU) | available | Only 4 vCPU |
| Hetzner CCX33 | 8 dedicated / 32 GB / 240 GB | dedicated AMD | €138.49 / $162.99 (EU); €140.99 (US) | available | Most predictable CPU; over-provisioned RAM |
| Hetzner primary IPv4 | - | - | €0.50 / $0.60 | - | Add to any Hetzner option |
| **DigitalOcean Basic** | 8 / 16 GiB / 320 GiB SSD, 6,000 GiB transfer | shared | **$96.00** ($0.14286/h) | - | Fallback (US/EU regions) |
| DigitalOcean CPU-Optimized | 8 dedicated / 16 GiB / 100 GiB | dedicated | $168.00 ($0.25/h) | - | If shared CPU misses the SLO |
| DigitalOcean General Purpose | 8 dedicated / 32 GiB / 100 GiB | dedicated | $252.00 ($0.375/h) | - | Over-provisioned |
| Fly.io shared-cpu-8x, 16 GB | 8 shared / 16 GB | shared: baseline 5 ms per 80 ms (6.25%) per vCPU, burst balance | **≈ $85.59 / 30 d** (iad); ≈ $98.76 (fra) | - | **Rejected**: sustained inference throttles to baseline |
| Fly.io performance-8x, 16 GB | 8 / 16 GB | performance (100%) | **≈ $248.00 / 30 d** (iad); ≈ $286.16 (fra) | - | Rejected: cost, and Compose `volumes:` ignored (ephemeral overlay) |
| Oracle Always Free (Ampere A1) | **2 OCPU / 12 GB** (Always Free tenancy equivalent of 1,500 OCPU-h + 9,000 GB-h/month); 200 GB block storage; 10 TB egress | Arm (A1: 1 OCPU = 1 thread) | $0 | capacity-limited ("out of host capacity") | **Rejected**: below target; idle reclamation |
| Oracle A1 pay-as-you-go, 8 OCPU / 16 GB | 8 / 16 GB | Arm | $0.01 per OCPU-h + $0.0015 per GB-h = **≈ $75.92/mo before free allowance**; ≈ $47.42 after the docs' allowance; ≈ $28.40 if the price-list tiers apply | capacity risk | Not recommended (Arm images, capacity, account friction) |

How these numbers were obtained:

- **Hetzner.** From the live price JSON behind hetzner.com (`/_resources/app/data/app/live_data_prices.json`), mapped to plans through each plan's `product-key`. Hetzner's storage pages state prices are exclusive of VAT; that the cloud-server prices are also net is assumed (**UNVERIFIED — check at order time**). Plan specs come from the plan pages. The "not available" labels were on the Cost-Optimized page at access time.
- **DigitalOcean.** Read from the Droplet pricing page text (Basic 8/16 $96; CPU-Optimized 8/16 $168; General Purpose 8/32 $252).
- **Fly.io.** Computed from constants in the pricing page source:
  - shared $0.00000075 per vCPU-second, including 0.25 GB per vCPU;
  - performance $0.00001196 per vCPU-second, including 2 GB per vCPU;
  - extra RAM $0.00000193 per GB-second;
  - 30-day month; regional markup iad ×1.0, fra ×1.1538.
  - The CPU baseline and burst behaviour are from Fly's CPU Performance doc. The Compose volume behaviour is from Fly's Multi-container Machines doc (Pilot init required).
- **Oracle.**
  - The Always Free docs page states the 1,500 OCPU-hour and 9,000 GB-hour allowance ("for Always Free tenancies, this is equivalent to 2 OCPUs and 12 GB"). It also states the idle rule: over 7 days, 95th-percentile CPU < 20% **and** network < 20% **and** (for A1) memory < 20% means the instance may be reclaimed.
  - Oracle's public price-list API still shows A1 free tiers of 0-3,000 OCPU-h and 0-18,000 GB-h. **The docs and the API disagree (UNVERIFIED which applies to a new tenancy).**
  - A1 PAYG is $0.01 per OCPU-hour and $0.0015 per GB-hour. For reference, A2 is $0.014/$0.002 and A4 is $0.0138/$0.0027 (A2/A4: 1 OCPU = 2 cores).

### F2. Caddy (docs, accessed 2026-09-26; latest release v2.11.4, 2026-06-03)

- **Automatic HTTPS** needs A/AAAA records pointing at the server, ports 80 and 443 open externally, and a writeable, persistent data directory. Behaviour:
  - Issuers are Let's Encrypt and ZeroSSL, with failover.
  - HTTP→HTTPS redirect by default.
  - Continuous background renewal.
  - HTTP-01 and TLS-ALPN-01 are on by default. DNS-01 needs a DNS-provider plugin and configuration.
  - Use a staging ACME endpoint while testing.
- **`reverse_proxy`:**
  - Sets or augments `X-Forwarded-For`, and sets `X-Forwarded-Proto` and `X-Forwarded-Host`.
  - **Ignores incoming `X-Forwarded-*` from untrusted clients.**
  - Flushes immediately for `Content-Type: text/event-stream` (SSE).
  - `header_up -Name` removes a request header.
  - Since 2.11.0 it rewrites `Host` for HTTPS upstreams.
- **Server options.** `trusted_proxies static <CIDRs>` (plus the `private_ranges` shorthand), `client_ip_headers` (default `X-Forwarded-For`), `trusted_proxies_strict`. `{client_ip}` is taken from those headers only for trusted peers.
- **Access logs.** `Cookie`, `Set-Cookie`, `Authorization` and `Proxy-Authorization` are logged as `REDACTED` by default. The `log_credentials` option turns that off, so leave it off.
- **`header` directive prefixes.** `?` sets a default only if the field doesn't already exist; `-` deletes; `>` defers. Defer is automatic with `?` and `-`.
- **`route` blocks** keep directives in the order written. Outside them, Caddy sorts directives by its built-in order, and this matters for "deny first" rules.

### F3. Cloudflare Free (docs, accessed 2026-09-26)

- **Timeouts.** Proxy Read Timeout is **125 s**; exceeding it returns HTTP 524, and only Enterprise zones can change it. Proxy Write Timeout 30 s, HTTP/1.1 keep-alive 400 s. SSE through Cloudflare therefore needs heartbeats well under 125 s.
- **Rate-limiting rules on Free:**
  - **1 rule**;
  - counting by **IP** only;
  - expression fields limited to **Path** and **Verified Bot**;
  - counting period **10 s** and mitigation timeout **10 s**.
- **Turnstile Free.** Up to 20 widgets, 10 hostnames per widget, unlimited challenges. Server-side token validation is required by design (the siteverify API). The plans page didn't cover it, so **confirm in the Turnstile docs**.
- **Trade-offs of proxying:**
  - Cloudflare terminates TLS and sees all traffic, including cookies and ticket text. That is acceptable for synthetic data but must be recorded as a third-party data flow (ASVS 14.2.3).
  - The real client IP must come from `CF-Connecting-IP` through Caddy `trusted_proxies` limited to Cloudflare's published ranges (ASVS 15.3.4).
  - The origin should only accept Cloudflare's ranges (provider firewall).

### F4. Backups and storage (accessed 2026-09-26)

- **restic** v0.19.1 (2026-07-05). Supports S3-compatible, B2, SFTP and REST backends. Repository data is encrypted client-side by design (**verify cipher details in the restic docs**), so an extra `age` layer is optional.
- **Backblaze B2:** from **$6.95 per TB per month**, first 10 GB always free, free egress up to 3× the average monthly stored data (then $0.01/GB), no minimum file size or duration fees, Class A/B/C calls free.
- **Cloudflare R2 Standard:** **$0.015 per GB-month**; Class A $4.50/million; Class B $0.36/million; free tier 10 GB-month storage, 1 M Class A and 10 M Class B per month; **egress free**.
- **Hetzner Storage Box BX11 (1 TB):** €3.20 / $4.00 per month (live feed). Hetzner Object Storage has a base price covering 1 TB storage + 1 TB egress, but it **was not rendered in the feed. UNVERIFIED.** Keep backups at a *different* provider than the VM.

### F5. Docker networking caveat (Docker docs, accessed 2026-09-26)

Docker routes traffic to published ports in the `nat` table, *before* the INPUT/OUTPUT chains that ufw manages. ufw rules are therefore effectively ignored for published ports. Rely on the **provider's firewall** (Hetzner Cloud Firewall / DO Cloud Firewall) and on publishing only Caddy's ports.

---

## DECISION / RECOMMENDATION

### D1. Host

1. **Primary.** Hetzner **CPX42** in NBG1 or HEL1, with a Primary IPv4, a Debian or Ubuntu LTS image (confirm the current LTS at build), Hetzner Cloud Firewall and backups off-provider.
2. **Cheaper variant.** If **CX43** is orderable at build time, benchmark it at P9 with the real stack:
   - triage p95 below the §7.7 15 s budget;
   - pipeline p95 below the §15 30 s SLO;
   - steal time acceptable.
   Keep it if it passes. That saves about €53/month.
3. **Fallback / US region.** DigitalOcean Basic 8/16 ($96). Use CPU-Optimized ($168) if shared CPU misses the SLO.
4. **Not used:** Fly.io (CPU throttling for sustained inference, ephemeral Compose volumes, cost) and Oracle Always Free (2 OCPU/12 GB, capacity, idle reclamation).

### D2. Topology on the VM

```
Internet ──(optional Cloudflare proxy)──> :443/:80 Caddy ──┬─> web:3000 (Next.js standalone, GET/HEAD only)
                                                           └─> api:8000 (FastAPI, /api/*)
internal network (no published ports): postgres, redis, ollama, worker, email-feed,
                                       otel-collector, tempo, prometheus, grafana
admin access: SSH (key-only, admin IP / Tailscale) → ssh -L for Grafana
```

Compose rules:

- Only `caddy` has `ports:`. All other services join `networks: { internal: { internal: true } }` (plus an `edge` network for caddy↔web/api). Spec §12.9 hardening applies: non-root, read-only rootfs, `cap_drop: [ALL]`, `no-new-privileges`, resource limits.
- Memory budget for 16 GB. **All figures are estimates, UNVERIFIED; measure at P9.**

  | Service | Limit |
  |---|---|
  | Ollama (1.5B Q4) | 3 GB |
  | worker (embedder + reranker + Presidio spaCy) | 3 GB |
  | postgres | 2 GB |
  | api | 768 MB |
  | web | 512 MB |
  | redis | 256 MB |
  | email-feed | 256 MB |
  | caddy | 128 MB |
  | observability (Collector 512M, Tempo 768M, Prometheus 768M, Grafana 384M) | ~2.4 GB |
  | **Total** | **≈ 13 GB**, leaving about 3 GB for the OS and page cache |

### D3. Caddyfile (`infra/caddy/Caddyfile`, Caddy 2.11.x)

```caddyfile
{
	email {$ACME_EMAIL}
	# acme_ca https://acme-staging-v02.api.letsencrypt.org/directory   # while testing
	servers {
		# Only when proxied by Cloudflare: paste Cloudflare's published IPv4/IPv6 ranges (refresh at deploy)
		# trusted_proxies static <cloudflare-ranges...>
		# client_ip_headers CF-Connecting-IP
	}
}

{$TW_PUBLIC_HOST} {
	# When proxied by Cloudflare, use DNS-01 instead (custom build with a Cloudflare DNS module; verify module + token scope):
	# tls { dns cloudflare {env.CF_API_TOKEN} }

	encode zstd gzip
	request_body {
		max_size 1MB                      # app enforces 256 KB for tickets (spec §11)
	}

	header {
		Strict-Transport-Security "max-age=63072000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
		Cross-Origin-Opener-Policy "same-origin"
		Cross-Origin-Resource-Policy "same-origin"
		# Fallback CSP for responses that don't set one (API JSON, static files, errors); Next.js sets the page CSP.
		?Content-Security-Policy "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
		-Server
		-X-Powered-By
	}

	# Strip headers that clients must never control (see nextjs-security.md)
	request_header -X-Middleware-Subrequest
	request_header -Content-Security-Policy
	request_header -X-Nonce

	# Named matchers (site-scoped)
	@internal path /api/v1/metrics /api/v1/metrics/ /api/docs* /api/redoc* /api/openapi.json /_next/image*
	@next_unsafe {
		not path /api/*
		not method GET HEAD
	}

	route {
		# 1) deny-first: internal and unused endpoints are never reachable from the Internet
		respond @internal 404

		# 2) Next.js serves pages only: no POST/PUT/... (no Server Actions; all mutations go to FastAPI)
		respond @next_unsafe 405

		# 3) API (SSE flushes immediately for text/event-stream)
		reverse_proxy /api/* api:8000 {
			header_up X-Real-IP {client_ip}   # overwrite; the API trusts X-Real-IP only from the Caddy container IP
		}

		# 4) everything else -> Next.js
		reverse_proxy web:3000 {
			header_up X-Real-IP {client_ip}
		}
	}

	log {
		output stdout
		# Cookie/Authorization are REDACTED by default (do not enable log_credentials).
		# Drop the ticket search term from access logs (ASVS 14.2.1); verify filter syntax for 2.11:
		format filter {
			request>uri query {
				delete q
			}
		}
	}
}
```

App side: `ClientIPMiddleware` uses `X-Real-IP` only when the TCP peer is Caddy's fixed internal IP, and otherwise the peer address. That value feeds rate limiting and audit `ip` (ASVS 15.3.4, 4.1.3).

### D4. Cloudflare: phased

- **Phase 1 (launch default).** DNS-only (grey cloud). Caddy obtains certificates with HTTP-01/TLS-ALPN-01. The provider firewall allows 80/443 from anywhere, and SSH only from the admin IP.
- **Phase 2 (turn on if abuse appears, or before sharing the link widely):**
  - Proxied (orange cloud), SSL mode "Full (strict)", Caddy on DNS-01.
  - Firewall allows 443 only from Cloudflare's ranges.
  - Caddy `trusted_proxies` = Cloudflare ranges with `client_ip_headers CF-Connecting-IP`.
  - Use the single Free rate-limit rule on `/api/v1/auth/` (block for 10 s above N requests per 10 s per IP; tune N).
  - Turnstile on `demo-login`.
  - SSE heartbeat every **20 s** (< 125 s read timeout).
  - Record Cloudflare in the data-flow and vendor list.

### D5. Demo-mode controls (`TW_DEMO_MODE=true`; startup validation refuses to boot if any is missing)

| Area | Control |
|---|---|
| Disclosure | Persistent banner on every page and the login page: synthetic data, don't enter real personal data, resets daily at 03:00 UTC. Taskmoor fictional disclaimer in the footer |
| Accounts | Seeded users per role (`agent.demo`, `ops.demo`, `csm.demo`, `eng.demo`, `admin.demo`). No sign-up. **`POST /api/v1/auth/demo-login {role}`** (per-IP limit, optional Turnstile), or published credentials. **No password change. No per-account lockout for demo users** (per-IP and global limits stay). MFA off for demo users (documented deviation) |
| Disabled mutations (403 `DEMO_MODE_FORBIDDEN`) | User CRUD and role changes; `PATCH /admin/org-settings` (frontier toggle/budget); model activation; policy rule-set activation (dry-run allowed); KB approve/publish/retire; `DELETE /tickets/{id}`; `POST /tickets/batch`; session "revoke-all" for other users |
| Allowed with quotas | Submit ticket (10/h per session), reprocess/regenerate (10/h), draft edit/approve ("mark sent" only; S-01), escalate/handoff edit, feedback, PII reveal (synthetic data; audited; 10/h) |
| Global caps | 200 new tickets/day. Queue depth > 20 → 429 `RATE_LIMITED` with `Retry-After`. Worker `max_jobs=2`. §7.7 timeouts |
| Input | Demo override `TW_DEMO_MAX_MESSAGE_CHARS=8000` (spec default 20k); subject 300; no attachments; simulated email feed only (S-12) |
| Frontier | Off by default. If on: `FRONTIER_DAILY_BUDGET_USD=1.00` (demo override of the §7.5 default 2.00), per-ticket cap $0.05, **plus** an Anthropic workspace spend limit as a hard backstop |
| Sessions | 4 h absolute, 60 min idle (see `auth-cookie-jwt-csrf.md` D5) |
| Hidden surfaces | Swagger/OpenAPI off; Grafana/Tempo/Prometheus internal only; `/api/v1/metrics` 404 at the edge |
| Robots | `X-Robots-Tag: noindex` on app routes (the landing/README page may be indexable) |

### D6. Abuse-protection layers

1. **Edge** (Phase 2): Cloudflare proxy, 1 IP rate-limit rule, Turnstile.
2. **Caddy:** 1 MB bodies; GET/HEAD-only to Next.js; internal paths 404; strip spoofable headers; the real IP is propagated.
3. **App rate limits:** `limits` **sliding-window counter** on Redis. It has no token bucket (see `auth-cookie-jwt-csrf.md` SI-A12). Limits:
   - per IP: auth 5/min, 50/day; other routes 120/min;
   - per user or session: the quotas in D5;
   - global: daily caps and the login circuit breaker (300/min).
4. **Work shaping:** queue-depth backpressure, worker concurrency, per-stage timeouts, frontier budget and circuit breaker.
5. **Content:** Presidio masking before any model or log call; banner warning; nightly purge.
6. **Detection:** alert on 429 spikes, `tw_jobs_queue_depth > 20` for 10 min, frontier budget < 20%, CPU > 90% for 15 min, disk > 80%, and certificate expiry < 14 days (Caddy renews automatically, so this alert is a safety net).

### D7. Nightly reset (`scripts/demo_reset.py`, `make demo-reset`, systemd timer at 03:00 UTC)

1. `SET tw:maintenance 1`. The API returns 503 `MAINTENANCE` to mutations and the UI shows a banner.
2. `docker compose stop worker email-feed` (drain: wait until arq has no running jobs, or 60 s).
3. Restore the **golden dump**: `pg_restore --clean --if-exists --no-owner -d ticketward /srv/golden/golden.dump`.
   - The dump is built at deploy from the idempotent seed, and its SHA-256 is verified before the restore.
   - It already contains the three processed demo tickets (§17), so the demo starts "ready".
4. `FLUSHDB` the app Redis DB. That clears sessions, revoked sids, rate-limit counters and queued jobs. Every visitor session ends.
5. `docker compose start worker email-feed`. The worker rebuilds the bm25 index on start (L-16).
6. Smoke test: `scripts/smoke_demo.py` runs the 3 demo tickets through the API and asserts the expected policy paths. On failure, alert and follow `docs/runbooks/demo-reset.md`.
7. `DEL tw:maintenance`. Write the audit event `demo.reset_completed`; a new audit hash chain starts from the golden state (documented).
8. **Then** run the nightly backup (D9). The backup captures the clean state, not visitor content.

### D8. Budget (monthly, prices as of 2026-09-26)

| Item | Cost |
|---|---|
| VM: Hetzner CPX42 + IPv4 | €69.99 (Hetzner USD list: $82.59); assumed net of VAT (UNVERIFIED) |
| Backups: B2 or R2, < 10 GB | $0 within free tiers (beyond: $6.95/TB-mo B2 or $0.015/GB-mo R2) |
| Cloudflare Free (optional) | $0 |
| Frontier (Anthropic) | $0 when off; worst case $1.00/day ≈ $30.4/month when on |
| Langfuse | $0 (off in demo) |
| Domain | **UNVERIFIED** (registrar- and TLD-dependent; roughly tens of USD per year) |
| **Total** | **≈ $83 (frontier off) to ≈ $113 (frontier on at cap)** + domain + VAT |

With CX43 (if available and it passes the benchmark), the VM line drops to €16.49 incl. IPv4 ($19.09).

### D9. Backups and restore

- **Nightly** (after the reset):

```bash
pg_dump -Fc -d "$TW_DB_URL_BACKUP" -f /srv/backup/tw-$(date -u +%F).dump
restic -r "s3:https://<b2-or-r2-endpoint>/<bucket>/ticketward" backup /srv/backup /srv/ticketward/config --tag nightly
restic -r "..." forget --keep-daily 14 --keep-weekly 4 --prune
```

- **Weekly:** `restic check --read-data-subset=5%`.
- **Monthly drill:** restore the latest snapshot into a scratch database, `pg_restore`, run the smoke test, and record RTO/RPO in `system-status.md`. This covers the P9 exit criterion "restore drill passes", with a target of RTO 1 h / RPO 24 h.
- **Credentials:** the bucket-scoped application key and the restic repository password live in Docker secrets, not the image. Keep a copy of the restic password **off the VM** (a password manager). A lost password means lost backups.
- **What is backed up:** the golden dump, `compose.prod.yaml`, the Caddyfile, and the encrypted (SOPS/age) secrets bundle. Model artefacts come back from HF Hub and KB sources from git (spec §15).

### D10. Host hardening and deploy

- SSH keys only, `PermitRootLogin no`. Admin access from a fixed IP or Tailscale; SSH is otherwise closed in the provider firewall.
- Automatic security updates plus a weekly reboot window. Docker Engine and the compose plugin from Docker's repository. Docker log driver `local` with rotation.
- **Deploy** (spec §14.5 step 11; GitHub environment with manual approval):
  1. SSH with a dedicated deploy key.
  2. `cosign verify` the GHCR images.
  3. `docker compose -f compose.prod.yaml pull && docker compose -f compose.prod.yaml up -d`.
  4. Run the smoke test.
  5. Roll back by re-pinning the previous image digests.
- **Secrets:** SOPS + age-encrypted `secrets.enc.yaml` in the ops repo, decrypted on the host into `/run/secrets` files (mode 0400). Rotation per `docs/runbooks/rotate-secrets.md`. This covers ASVS 13.3.1 partially; see `owasp-asvs-l2.md`.

---

## SPEC IMPACT

Disposition in spec v1.1: every item below was applied (A-23; demo mode as ADR-0035, host options in ADR-0026). The host choice itself is deferred to P9 by owner decision D-06.

| # | Spec location | Finding | Recommendation |
|---|---|---|---|
| SI-D1 | §12.6 "Fly secrets / Doppler / 1Password"; host shortlist | Fly.io is unsuitable (6.25% shared-CPU baseline; Compose volumes ephemeral). Oracle Always Free is now 2 OCPU/12 GB | Drop Fly and Oracle from the shortlist; use SOPS+age (or 1Password/Doppler) for host secrets |
| SI-D2 | §15 backup "nightly pg_dump (demo), 14 daily + 4 weekly" vs §16 P11 nightly reset | Backing up before the reset keeps visitor-entered (possibly real) personal data for up to 6 weeks | For the public demo, back up **after** the reset (clean state). Keep full-content backups for non-demo environments only |
| SI-D3 | §16 P11 "read-only seeded users per role" | The demo flow (§17) needs writes (submit, edit, approve, escalate) | Define demo accounts as **immutable accounts with quota-limited workflow writes and disabled admin mutations** (D5) |
| SI-D4 | §11 login lockout; §16 P11 shared demo users | Per-account lockout on shared demo accounts is a trivial DoS; password change would lock everyone out | No per-account lockout and no password change for demo users; `demo-login` endpoint (a new auth pathway to document; ASVS 6.1.3) |
| SI-D5 | §11 "Redis token bucket via `limits`" | `limits` has no token bucket | Sliding-window counter (see SI-A12) |
| SI-D6 | §11 `GET /metrics` | Must never be reachable from the Internet | Internal port (SI-O2) **and** an edge 404 for `/api/v1/metrics` |
| SI-D7 | §7.1 "same-site via reverse proxy" | If Cloudflare proxies, a third party terminates TLS; client IP must come from trusted headers | Record Cloudflare as a data processor; Caddy `trusted_proxies` + `CF-Connecting-IP` → `X-Real-IP` |
| SI-D8 | §11 SSE `/tickets/{id}/events` | Cloudflare returns 524 after 125 s without bytes | SSE heartbeat every 20 s |
| SI-D9 | §16 P11 "frontier capped at $1/day" vs §7.5 default 2.00 | Two different values | Explicit demo override `FRONTIER_DAILY_BUDGET_USD=1.00` + Anthropic workspace spend limit |
| SI-D10 | §6/§12.2 field limits (20k chars) | Too generous for a public CPU-bound demo | Demo override `TW_DEMO_MAX_MESSAGE_CHARS=8000` |

---

## IMPLEMENTATION CHECKLIST

- [ ] P9: order the VM (CPX42; check CX43 availability first). Provider firewall; DNS A/AAAA; SSH hardening.
- [ ] P9: `compose.prod.yaml` with internal networks, resource limits and healthchecks. Only Caddy publishes ports.
- [ ] P9: Caddyfile (D3) + tests: `curl -X POST /` → 405; `/api/v1/metrics` → 404; security headers on HTML, API, static and 404 responses; an HTTP request is redirected; the `X-Real-IP` spoof is overwritten.
- [ ] P9: CPU benchmark (triage and pipeline p95) on the chosen SKU; memory measurement per container.
- [ ] P9: restic + B2/R2 bucket, scoped key; nightly/weekly jobs; first restore drill logged.
- [ ] P11: `TW_DEMO_MODE` controls (D5) with startup validation; `demo-login`; quotas; banner.
- [ ] P11: systemd timer + `scripts/demo_reset.py` + golden dump build step in the release pipeline + `smoke_demo.py`.
- [ ] P11: alerts (D6) wired into Grafana alerting; runbooks `demo-reset.md`, `restore-db.md`, `rotate-secrets.md`.
- [ ] P11: decide Cloudflare Phase 2 (DNS-01 build, origin lock-down, rate rule, Turnstile, SSE heartbeat verification through CF).

---

## OPEN RISKS / TO VERIFY

- **Prices and availability change.** Hetzner's Cost-Optimized line showed "not available" at access time, and its prices differ sharply from Regular Performance. **Re-check all prices at order time.** VAT treatment of the cloud-server prices is **UNVERIFIED**.
- **Oracle free-tier allowance:** the docs (1,500/9,000) and the price-list API (3,000/18,000) disagree. **UNVERIFIED.**
- **Shared-vCPU performance** (CPX42 / DO Basic) for CPU LLM inference is unknown until the P9 benchmark. Dedicated options (DO CPU-Optimized, CCX33) are the escape hatch.
- **Caddy log `format filter` syntax** and the Cloudflare DNS module for DNS-01 need verification against Caddy 2.11. Cloudflare's IP ranges must be refreshed at each deploy.
- **Turnstile server-side validation** details were not confirmed on the plans page. **Verify in the Turnstile docs.**
- **Domain cost** is not researched. **UNVERIFIED.**
- **restic cipher and design details** were not re-read for this document. **Verify in the restic docs.**
- **Abuse content.** A public text box can receive offensive or illegal content. The nightly purge plus the banner reduce exposure. Consider a simple moderation filter if abuse is observed.

---

## LINKED ADR

- **ADR-0026** (Docker Compose + Caddy; single-VM public demo): host choice with dated prices, the Cloudflare phase plan, demo-mode controls, reset-then-backup ordering.
- Cross-refs: ADR-0020 (demo-login, demo-account lockout policy), ADR-0015 (frontier demo budget), ADR-0024 (internal-only observability), ADR-0027 (deviations: internal TLS, off-host logs, secrets).

---

## SOURCES (all accessed 2026-09-26)

- Hetzner: [Cloud overview](https://www.hetzner.com/cloud/), [Cost-Optimized](https://www.hetzner.com/cloud/cost-optimized/), [Regular Performance](https://www.hetzner.com/cloud/regular-performance/), [General Purpose](https://www.hetzner.com/cloud/general-purpose/), live price feed `https://www.hetzner.com/_resources/app/data/app/live_data_prices.json`, [Storage Box](https://www.hetzner.com/storage/storage-box/), [Object Storage](https://www.hetzner.com/storage/object-storage/) (VAT statement)
- [DigitalOcean Droplet pricing](https://www.digitalocean.com/pricing/droplets)
- Fly.io: [pricing](https://docs.fly.io/about/pricing/), [CPU performance](https://docs.fly.io/machines/cpu-performance/), [Multi-container Machines](https://docs.fly.io/machines/guides-examples/multi-container-machines/)
- Oracle: [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), price-list API `https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?currencyCode=USD`, [Compute shapes / OCPU definition](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm)
- Caddy: [automatic HTTPS](https://caddyserver.com/docs/automatic-https), [reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy), [global options (trusted_proxies, client_ip_headers, log_credentials)](https://caddyserver.com/docs/caddyfile/options), [request_header](https://caddyserver.com/docs/caddyfile/directives/request_header), [header](https://caddyserver.com/docs/caddyfile/directives/header), [route](https://caddyserver.com/docs/caddyfile/directives/route), [releases](https://github.com/caddyserver/caddy/releases)
- Cloudflare: [connection limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/), [rate limiting rules](https://developers.cloudflare.com/waf/rate-limiting-rules/), [Turnstile plans](https://developers.cloudflare.com/turnstile/plans/), [R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Backblaze B2 pricing](https://www.backblaze.com/cloud-storage/pricing)
- [restic releases](https://github.com/restic/restic/releases)
- [Docker: packet filtering and firewalls (ufw caveat)](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
- [limits strategies](https://limits.readthedocs.io/en/stable/strategies.html)

---

**Change log**: 2026-09-27: status and spec-impact disposition updated to spec v1.1 (A-23, D-06); identifiers renamed for Ticketward.

**Document Version**: 1.1
**Next Update**: P9 (SKU benchmark and final order) and P11 (Cloudflare Phase 2 decision)
