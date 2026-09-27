---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: spec §7.5, §11 (breached-password check), §12.1, §12.3, §12.4, §12.11, §13 S-01, §14.2, §16 P9, §24.2; research public-demo-deployment, owasp-asvs-l2
informed: operators (allow-list changes); contributors (outbound HTTP only through core/http.py or provider adapters)
supersedes: none
amended: none
---

# ADR-0036: Egress allow-list enforced by an egress-proxy container

## Context and Problem Statement

Ticketward's only legitimate outbound destinations are:
* the Anthropic API (frontier drafting, when enabled);
* the Hugging Face Hub (fetching pinned model artifacts at build or model-fetch time);
* optionally, the HIBP range API (online breached-password check).

Everything else is a risk:
* SSRF (A01:2025, CWE-918);
* exfiltration by an injected prompt;
* a compromised dependency phoning home;
* an accidental "send" integration that would break S-01 (no auto-send).

The Rule-of-Two assessment relies on Ticketward having **no external communication** beyond the allow-listed
providers (threat model).

In v1.0 the allow-list was a coding rule (HTTP clients only in allow-listed adapters), checked statically by
T-NO-SEND, but nothing enforced it at the network level. The spec review (A-25(d)) asked for enforcement. ASVS
13.2.4/13.2.5 require an allow-list of external systems, configured at the server.

How is the outbound allow-list enforced, so that a library or code path that ignores it cannot reach the internet?

## Decision Drivers

* Enforcement by construction: no route to the internet, rather than "please use the proxy".
* Hostname-based rules: vendors sit behind CDNs with changing IPs.
* End-to-end TLS to vendors (no TLS interception, no CA injection).
* Testable in CI and in the Compose stack, with denials logged as security events.
* Low operational cost on a single host.

## Considered Options

1. An egress-proxy container as the only path to the internet; app containers have no internet route (chosen)
2. Host firewall rules only
3. Per-library allow-lists (configuration in code)
4. No enforcement

## Decision Outcome

Chosen option: the egress-proxy container (spec §12.11), because a network without a route makes the allow-list
fail closed. A client that ignores the proxy simply cannot connect, and hostname rules live in one reviewed file.

**Networks (Compose, built in P9):**

| Network | Members | Route to the internet |
|---|---|---|
| `edge` | Caddy ↔ web, API | none for web/API (see implementation note) |
| `internal` (`internal: true`) | Postgres, Redis, Ollama, API, worker, email-feed, observability, egress-proxy | none |
| `egress` | egress-proxy only | yes |

Only Caddy publishes ports (80/443).

**Proxy:**
* A forward proxy on its own network. App containers get `HTTPS_PROXY` (and `NO_PROXY` for internal service names).
* HTTPS is tunnelled with CONNECT, so TLS stays end-to-end to the vendor. The proxy sees only the destination host
  and port.
* The allow-list lives in `infra/egress-proxy/`, reviewed like code (CODEOWNERS).

**Allow-list (A-25(d)):**
* `api.anthropic.com:443`;
* the Hugging Face Hub hosts, **for build and model-fetch jobs only**. The exact host list (API host plus download
  and CDN hosts) is verified at P9, because HF storage back-ends change;
* `api.pwnedpasswords.com:443`, only when the online breached-password check is enabled;
* Cloud Langfuse is off.

The proxy logs every denial, which becomes the security event `egress.denied` and is alerted on.

**Clients:**
* Outbound HTTP clients are built only in `core/http.py` (egress proxy, timeouts) or inside provider adapters. The
  T-NO-SEND static test enumerates every HTTP-client construction site.
* No user-supplied URL is ever fetched.

**Implementation notes (P9; reported to the lead for a spec clarification):**
* **`edge` must not give web/API a route.** A default bridge network is routable. `edge` is therefore declared
  `internal: true` too. Caddy, which must publish ports and reach its ACME CA (and the Cloudflare API for DNS-01 in
  Phase 2), is the only other container attached to a routable network. Its outbound use is limited to ACME. The spec
  wording "only the egress-proxy container has a route to the internet" does not account for Caddy.
  *Today (P0) `edge` is a default bridge and the API has a direct route; this closes in P9.*
* **Alert delivery and off-host log shipping** (Grafana e-mail/ntfy, security-log sink) need outbound paths that are
  not on the allow-list. At P9 they are either added as per-client proxy rules for the observability containers only,
  or run from the host.
* **HF only for model-fetch:** enforced by a per-client rule (source identity or proxy credentials), chosen with the
  proxy product at P9 (for example Squid, Smokescreen or Envoy; not fixed by the spec).
* **DNS as a side channel:** verify at P9 whether Docker's embedded DNS forwards external lookups from `internal: true`
  networks on the installed Engine version. If it does, it is a residual low-bandwidth exfiltration channel, recorded
  in the threat model.

### Consequences

* Good, because exfiltration and SSRF paths from app containers are closed at the network level. A new dependency that
  phones home fails loudly, not silently.
* Good, because the Rule-of-Two "no external communication" property is enforced, not only reviewed. S-01 gains a
  second, independent control.
* Good, because the allow-list is one reviewed file, and denials are visible as security events.
* Bad, because there is one more container to run and monitor. If it is down, the frontier and HIBP fail. The existing
  fallbacks cover this: `model_unavailable` handling, the local draft, and the offline breached list.
* Bad, because vendor hostnames can change (especially HF download hosts). Allow-list maintenance is a recurring
  task, surfaced by denial alerts during model fetch.
* Neutral, because the proxy cannot inspect CONNECT-tunnelled content. That is intentional (end-to-end TLS). Content
  controls stay in the app: masking before the frontier, and token caps.

### Confirmation

* `T-SEC-EGRESS` (Compose integration test):
  * from `api` and `worker`, a request to a non-allow-listed host fails at the proxy (403);
  * a direct TCP connection to a public IP fails (no route);
  * `api.anthropic.com` succeeds through CONNECT;
  * HF Hub succeeds only from the model-fetch job.
* `T-SEC-COMPOSE-policy` (parses `compose.prod.yaml`):
  * only Caddy publishes ports;
  * only the egress-proxy (and Caddy) join routable networks;
  * `internal` and `edge` are `internal: true`.
* T-NO-SEND (static + API test): no SMTP or e-mail SDK in any dependency tree; every HTTP-client construction site is
  enumerated and uses `core/http.py` or a provider adapter.
* An `egress.denied` alert rule fires on a synthetic denial in the P9 drill.
* The P9 exit review records the verified HF host list, the chosen proxy product, and the DNS behaviour.

## Pros and Cons of the Options

### Egress-proxy container, no internet route for apps (chosen)

* Good, because it fails closed by construction, uses hostname rules, keeps TLS end-to-end, and is testable in
  Compose.
* Bad, because of the extra container, allow-list upkeep, and the Caddy/alerting special cases.

### Host firewall rules only

* Good, because there is no extra container.
* Bad, because rules are IP-based (vendor CDNs rotate IPs), Docker's NAT rules are easy to get wrong, they are hard
  to test in CI, and they drift from the documented list.

### Per-library allow-lists (configuration in code)

* Good, because it is simple and already partly true (base URLs in adapters).
* Bad, because it is not enforcement. Any transitive library, new code path or injected configuration bypasses it.

### No enforcement

* Good, because it has zero cost.
* Bad, because every exfiltration and SSRF path stays open, and the Rule-of-Two claim becomes unverifiable.

## More Information

* Spec (private): §7.5 (frontier client), §11 (HIBP through the proxy), §12.1 (boundaries), §12.3 (SSRF), §12.4
  (Rule of Two), §12.11 (networks, egress proxy, internal TLS), §13 S-01 (T-NO-SEND), §14.2 (`core/http.py`), §16 P9,
  §24.2 (edge). Change record A-25(d), A-25(h).
* Research: [public-demo-deployment](../research/public-demo-deployment.md),
  [owasp-asvs-l2](../research/owasp-asvs-l2.md) (13.2.4/13.2.5, 1.3.6).
* Related ADRs: ADR-0015 (Anthropic client), ADR-0020 (breached-password check), ADR-0024 (observability), ADR-0026
  (host and networks), ADR-0034 (model fetch of gated weights).
* Security docs: [threat model](../security/threat-model.md) (E-16 egress proxy, Rule of Two), [audit
  events](../security/audit-events.md) (`egress.denied`).
* Revisit when: a new outbound integration is proposed (it needs an ADR amendment and an allow-list PR), the deployment
  becomes multi-host, or the proxy product changes.
* Status history: 2026-09-27 Accepted (new in spec v1.1, change record A-25(d)).
