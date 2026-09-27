# infra/otel/ (planned in P7)

`collector.yaml` for the OpenTelemetry Collector (spec §15): OTLP receiver from the API and
arq workers, batch processor, attribute filtering that enforces the same allow-list as log
redaction (no ticket text, no PII), and export to Tempo (Jaeger in dev). Runs under the
`observability` Compose profile on the internal network. Details are settled by the ERPROT
topic `observability-otel.md`.
