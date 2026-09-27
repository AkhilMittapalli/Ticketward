# infra/grafana/ (planned in P7)

Provisioned dashboards (`dashboards/*.json`, spec §15): (1) service health (RED),
(2) pipeline and model (stage latency, validity, decisions, cost), (3) quality (feedback
rates, override by intent), (4) KB health (stale documents, coverage gaps), (5) security
events. Datasources are provisioned from files; no credentials are committed.
