# infra/prometheus/ (planned in P7)

`prometheus.yml` scraping the API/worker `/metrics` endpoints on the internal network only
(never exposed through the reverse proxy). Metric names follow spec §15 (`tw_http_*`,
`tw_pipeline_*`, `tw_llm_*`, `tw_kb_*` ...). Alert rules: multi-window burn rate on API
availability, queue depth > 20 for 10 min, frontier budget < 20%, stale KB > 10.
