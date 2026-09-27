---
status: Accepted
date: 2026-09-27
decision-makers: Akhil Mittapalli (owner)
consulted: brief §8, §11, §13; spec §12.6, §12.9, §12.11, §14.1, §14.5, §15, §16 P9/P11, §24; research public-demo-deployment, python-packaging
informed: reviewers (clean-clone quick start); operators
supersedes: none
amended: 2026-09-27 (spec v1.1)
---

# ADR-0026: Docker Compose and Caddy; single-VM public demo (host decided at P9)

> **Amended in spec v1.1 (2026-09-27; change record D-06, A-23, A-24, A-25(d)(m), A-28, A-29(e)).**
> * **The host is decided at P9**, after the CPU latency benchmark on the real stack (D-06). Options with prices dated
>   2026-09-26 are listed below: Hetzner CPX42 recommended; Fly.io and Oracle Always Free rejected. The decision is
>   recorded here.
> * **Cloudflare is phased:**
>   * Phase 1 is DNS-only (the launch default);
>   * Phase 2 is proxied, with Full (strict), DNS-01, the origin firewall limited to Cloudflare ranges, and
>     `trusted_proxies` + `CF-Connecting-IP`;
>   * if proxied, Cloudflare is recorded as a TLS-terminating third party.
> * **Edge rules** in the Caddyfile (§24.2). **Nightly reset, then backup** in the demo (ADR-0035).
> * **Networks:** `edge`, `internal` (`internal: true`) and `egress`. Only the **egress proxy** has an outbound route
>   for app containers (ADR-0036). Caddy also needs a routable network for its published ports and ACME, as ADR-0036's
>   implementation note records. **Only Caddy publishes ports** (80/443). P0 has built `edge` and `internal`; `egress`
>   and the proxy arrive in P9.
> * **Compose layout:** core services have no profile; `compose.override.yaml` is auto-loaded in dev (ports bound to
>   127.0.0.1); prod uses `-f compose.prod.yaml`; `TW_ENV` defaults to `prod`. Base image
>   `python:3.12-slim-trixie` by digest.
> * **Host hardening** has a runbook (`host-hardening.md`), which this ADR previously flagged as missing. **Deploy**
>   is SSH + cosign verify + digest rollback. **Secrets** use SOPS + age.

## Context and Problem Statement

The brief says "Docker Compose, then a public sanitized deployment" (brief §8). Its first definition-of-done item is
that a reviewer can run the project locally with Docker Compose and seeded synthetic data (brief §13): clean clone to
working UI in ≤ 15 min, verified by the CI `compose` smoke job (DoD-1, BR-067).

Services:
* Caddy (2.11.x);
* Next.js (standalone);
* the API (public listener + internal service-token listener);
* the worker (retrieval models, NLI verifier, injection detector, Presidio);
* the email feed;
* a one-shot `migrate`;
* PostgreSQL 16 + pgvector 0.8.6, Redis 7 (ACL), Ollama;
* the egress proxy;
* profiles `ml` (MLflow) and `observability` (Collector, Tempo, Prometheus, Grafana).

The public demo runs in demo mode (ADR-0035) on one VM of about 8 vCPU / 16 GB. The shared-vCPU performance of
candidate hosts is unknown (R-23).

How should Ticketward be packaged and deployed for local review and for the public demo?

## Decision Drivers

* One-command local run (DoD-1), proven in CI on every PR.
* Low cost and low operational burden for a solo owner, with a measured host choice (D-06).
* Hardened defaults: least privilege, segmentation, enforced egress, automatic TLS.
* A fit with CPU-bound inference (15–45 s jobs, SSE, a 16 GB model host).
* Backups that never capture visitor content in the demo, and measured RPO 24 h / RTO 1 h.

## Considered Options

1. Docker Compose + Caddy on a single VM; host chosen at P9 from dated options (chosen)
2. Kubernetes
3. Serverless
4. Fly.io
5. Oracle Cloud Always Free

## Decision Outcome

Chosen option: "Compose + Caddy on a single VM, host decided at P9", because it gives reviewers one command, keeps
the demo within about $83–113/month, and puts the whole security posture in two readable files (Compose and the
Caddyfile).

**Host options (prices read 2026-09-26; re-check at order time):**

| Option | Spec | Monthly | Status |
|---|---|---|---|
| Hetzner Cloud CPX42 (NBG1/HEL1) | 8 shared AMD vCPU, 16 GB, 320 GB NVMe | €69.49 + €0.50 IPv4 (≈ $82.6; VAT unverified) | **recommended** |
| Hetzner Cloud CX43 | same size, cost-optimized line | €15.99 (+ IPv4) | only if orderable **and** it passes the P9 benchmark |
| DigitalOcean Basic | 8 vCPU / 16 GiB shared | $96 | fallback / US region |
| DigitalOcean CPU-Optimized | dedicated CPU | $168 | if shared CPU misses the SLO |
| Fly.io, Oracle Always Free | – | – | rejected (see below) |

The P9 benchmark must show triage P95 within the 15 s budget, pipeline P95 within the 30 s SLO, and acceptable CPU
steal. The chosen host is then recorded in this ADR's status history.

**Topology and edge (spec §12.11, §24.2):**
* Networks: `edge` (Caddy ↔ web/API), `internal` (`internal: true`: Postgres, Redis, Ollama, API, worker, email
  feed, observability), and `egress` (only the egress proxy). Only Caddy publishes 80/443. Admin access is key-only
  SSH from a fixed IP or Tailscale, with Grafana through an SSH tunnel.
* Caddyfile edge rules:
  * a global body cap of 3 MB (just above the 2 MB batch limit);
  * `respond 404` for `/api/v1/metrics`, `/api/docs*`, `/api/redoc*`, `/api/openapi.json` and `/_next/image*`;
  * `respond 405` for any non-GET/HEAD request that is not `/api/*`;
  * strip client-supplied `Content-Security-Policy`, `X-Nonce` and `X-Middleware-Subrequest`;
  * overwrite `X-Real-IP` (trusted by the API only from Caddy/web internal addresses);
  * security headers and the fallback CSP; `-Server`, `-X-Powered-By`;
  * access logs drop `q`; SSE flushes immediately.
* Certificates: Let's Encrypt with ZeroSSL fallback, a staging CA while testing, and a persistent data directory.
* Containers: non-root UID 10001, read-only rootfs, `tmpfs /tmp`, `cap_drop: [ALL]`, `no-new-privileges`, resource
  limits, healthchecks (`ticketward/healthcheck.py`).
* **Internal TLS is a documented deviation** on the single host (ADR-0027). Any multi-host deployment must enable it.

**Host hardening and deploy (`docs/runbooks/host-hardening.md`, §24.6):**
* SSH keys only and `PermitRootLogin no`; SSH closed except for a fixed IP or Tailscale.
* Automatic security updates with a weekly reboot window.
* Docker Engine and the Compose plugin from Docker's repository, log driver `local` with rotation.
* Deploy: GitHub environment with manual approval → SSH deploy key → `cosign verify` of the GHCR images → `pull` +
  `up -d` → smoke test → roll back by re-pinning the previous digests.

**Secrets:** SOPS + age-encrypted bundle, decrypted on the host into Docker secret files (0400). The age key and the
restic password are kept off the VM (§12.6).

**Backups:** restic to B2 or R2 (14 daily + 4 weekly, weekly `restic check --read-data-subset=5%`, monthly restore
drill). In the demo, **after** the nightly reset. Backups hold only wrapped DEKs (ADR-0037).

### Consequences

* Good, because one command reproduces the stack anywhere Docker runs, and CI proves it on every PR.
* Good, because the posture is auditable in the Compose file and Caddyfile, and egress is actually enforced
  (ADR-0036).
* Good, because the host is chosen on measured latency, not assumed.
* Bad, because there is a single point of failure and no HA. That is acceptable for the 99.5% demo SLO.
* Bad, because host hardening, patching and backups are ours. The runbooks and monthly restore drill cover them.
* Bad, because if Cloudflare Phase 2 is enabled, a third party terminates TLS and sees plaintext traffic. It is
  recorded in the data-flow and vendor inventory, and Phase 1 (DNS-only) is the default.

### Confirmation

* CI `compose` smoke job (§14.5 step 10): `docker compose up -d --build` (no profile), stub LLM, seed, three demo
  tickets through the API, schema-valid outputs and the expected policy paths.
* `T-OPS-container-hardening` (proposed): `docker inspect` shows `User=10001`, `ReadonlyRootfs`, `CapDrop=[ALL]` and
  `no-new-privileges`, and only Caddy publishes ports.
* `T-SEC-EGRESS`: from app containers, a non-allow-listed host fails (ADR-0036).
* `T-SEC-EDGE-headers`: the edge 404/405 rules, header stripping and the fallback CSP.
* Trivy (fail on HIGH/CRITICAL with a fix), cosign-signed images, and signature verification in the deploy job.
* P9 exit: clean clone to green smoke in < 15 min; restore drill passes (RPO 24 h / RTO 1 h); the **host decision is
  recorded** with the benchmark numbers; a TLS scan is recorded.

## Pros and Cons of the Options

### Compose + Caddy on a single VM

* Good, because it is simple, cheap, reviewer-runnable and brief-aligned, with automatic TLS and a readable posture.
* Bad, because there is no HA and host security is self-managed.

### Kubernetes

* Good, because of HA, NetworkPolicies and rollouts.
* Bad, because it is heavy and costly for one demo box, adds misconfiguration surface, and makes DoD-1 harder.

### Serverless

* Good, because it scales to zero with managed patching.
* Bad, because CPU LLM inference, 15–45 s jobs, SSE and stateful Postgres/Redis don't fit, and it fails DoD-1.

### Fly.io

* Good, because it is a simple container PaaS.
* Bad, because of sustained-CPU throttling and ephemeral volumes for Compose-style state (research
  `public-demo-deployment`).

### Oracle Cloud Always Free

* Good, because it costs nothing.
* Bad, because it offers about 2 OCPU / 12 GB with reclamation risk, which is too small and unreliable for CPU
  inference.

## More Information

* Spec (private): §12.6 (secrets), §12.9 (containers), §12.11 (networks, egress, internal TLS), §14.1 (Compose
  layout), §14.5 (CI jobs, deploy), §15 (SLOs, backups, runbooks), §16 P9, P11, §19 DoD-1, DoD-12, DoD-13, §21 R-09,
  R-11, R-23, §24 (hosts, edge, demo mode, reset, backups, hardening). Change record D-06, A-23, A-24, A-25 (d)(m),
  A-28, A-29 (e).
* Brief (private): §8, §13. BR-061, BR-062, BR-067.
* Research: [public-demo-deployment](../research/public-demo-deployment.md),
  [python-packaging](../research/python-packaging.md) (base images).
* Related ADRs: ADR-0022, ADR-0023, ADR-0024, ADR-0027, ADR-0028, ADR-0035, ADR-0036, ADR-0037.
* Revisit when: at P9 (record the host), when the demo needs HA or multiple hosts, or when real authorised data raises
  the required assurance.
* Status history: 2026-09-26 Accepted (P0). 2026-09-27 amended for spec v1.1 (host decided at P9, Cloudflare phases,
  edge rules, egress network, reset-then-backup, host hardening, Compose layout).
