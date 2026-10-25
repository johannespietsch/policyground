"""Generate dashboards/policyground.json (run: python obs/grafana/build_dashboard.py).
Panels are code so they can be reviewed in diffs; the JSON is the provisioned artifact."""

import json
from pathlib import Path

PROM, LOKI, PG = {"type": "prometheus", "uid": "prom"}, {"type": "loki", "uid": "loki"}, \
    {"type": "grafana-postgresql-datasource", "uid": "pg"}
panels, y = [], 0


def row(title):
    global y
    panels.append({"type": "row", "title": title, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": False})
    y += 1


def panel(kind, title, targets, x, w, h=7, unit=None, ds=PROM, desc="", **extra):
    p = {"type": kind, "title": title, "description": desc, "datasource": ds,
         "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
         "fieldConfig": {"defaults": {"unit": unit} if unit else {}, "overrides": []}, "options": {}}
    p.update(extra)
    panels.append(p)
    return p


def prom(expr, legend=""):
    return {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": legend[:1].upper() or "A"}


def sql(q, fmt="table"):
    return {"datasource": PG, "rawSql": q, "format": fmt, "rawQuery": True, "editorMode": "code", "refId": "A"}


row("Request path")
panel("timeseries", "Questions per minute, by outcome",
      [prom('sum by (outcome) (rate(policyground_requests_total[5m])) * 60', "{{outcome}}")], 0, 8)
panel("timeseries", "Latency p50 / p95",
      [prom('histogram_quantile(0.5, sum by (le) (rate(policyground_request_seconds_bucket[5m])))', "p50"),
       prom('histogram_quantile(0.95, sum by (le) (rate(policyground_request_seconds_bucket[5m])))', "p95")],
      8, 8, unit="s")
panel("timeseries", "Cost and LLM calls per question",
      [prom('sum(rate(policyground_llm_cost_usd_total[15m])) / sum(rate(policyground_requests_total[15m]))', "USD / question"),
       prom('sum(rate(policyground_llm_calls_total[15m])) / sum(rate(policyground_requests_total[15m]))', "LLM calls / question")],
      16, 8, desc="LLM calls / question above 1 means regenerates (validator rejections). Capped at 2 (D27).")
y += 7
panel("timeseries", "Abstain rate (alert: > 2x baseline 14%)",
      [prom('policyground:abstain_rate:15m', "abstain rate")], 0, 8, unit="percentunit",
      desc="Recording rule over 15m. AbstainRateHigh fires above 0.28 with >= 10 questions.")
panel("timeseries", "Abstentions by reason",
      [prom('sum by (reason) (increase(policyground_abstentions_total[15m]))', "{{reason}}")], 8, 8,
      desc="validator = forced abstain after rejected regenerate (INCIDENTS #10); unresolved_property = name match failed (D22).")
panel("timeseries", "Tokens per question / validator rejections per question",
      [prom('sum by (direction) (rate(policyground_llm_tokens_total[15m])) / scalar(sum(rate(policyground_requests_total[15m])))', "tokens {{direction}}"),
       prom('sum(rate(policyground_validator_rejections_total[15m])) / sum(rate(policyground_requests_total[15m]))', "rejections")],
      16, 8)
y += 7

row("Pipeline health (M3/M4)")
panel("timeseries", "KG / vector disagreement",
      [prom('policyground_kg_vector_disagreement', "{{tenant}}")], 0, 8, unit="percentunit",
      desc="Share of properties whose KG value differs from the newest production chunks: the staleness window (M4).")
panel("stat", "Newest snapshot age",
      [prom('policyground_newest_snapshot_age_seconds', "{{tenant}}")], 8, 4, unit="s",
      desc="Since the newest production slice was ingested. A skipped nightly DAG run shows up here (INCIDENTS #8). SnapshotStale > 26h.")
panel("timeseries", "Stream: events applied / ignored per minute",
      [prom('sum by (outcome) (rate(policyground_stream_events_total[5m])) * 60', "{{outcome}}")], 12, 6,
      desc="ignored = version guard rejected a duplicate or out-of-order event (D34, INCIDENTS #9).")
panel("timeseries", "Stream: consumer lag by partition",
      [prom('policyground_stream_lag', "partition {{partition}}")], 18, 6)
y += 7
panel("table", "Ingested slices (rows / duplicates per snapshot)",
      [sql("SELECT snapshot_date, chunker, embedder, rows, duplicates, ingested_at FROM chunk_slices "
           "WHERE tenant='hotels' ORDER BY snapshot_date DESC, chunker LIMIT 12")], 0, 12, h=8,
      ds=PG, desc="duplicates > 0 = the INCIDENTS #7 failure mode (non-idempotent re-run).")
panel("table", "DAG eval task (eval_runs, retrieval only)",
      [sql("SELECT snapshot_date, chunker, chunk_rows, round((metrics->>'doc@5')::numeric,2) AS \"doc@5\", "
           "round((metrics->>'fact@5_filtered')::numeric,2) AS \"fact@5 filt.\", left(source, 40) AS source, created_at "
           "FROM eval_runs ORDER BY id DESC LIMIT 12")], 12, 12, h=8, ds=PG)
y += 8

row("Eval and drift (M4)")
panel("table", "Drift runs: score vs noise band",
      [sql("SELECT created_at, mutation, phase, graph, round(mean::numeric,2) AS mean, "
           "round(band_lo::numeric,2) AS band_lo, round(band_hi::numeric,2) AS band_hi, verdict "
           "FROM drift_runs ORDER BY created_at DESC LIMIT 12")], 0, 24, h=8, ds=PG,
      desc="Probe set about exactly the mutated properties (D35). Band = mean +- 2 sigma, floored at sampling error (D37).")
y += 8

row("Logs (Loki) - filter by request_id, then search the same id in Phoenix (session)")
panel("logs", "API: questions (one line per /ask)",
      [{"datasource": LOKI, "expr": '{service="api"} |= "\\"msg\\": \\"ask\\"" | json', "refId": "A"}],
      0, 12, h=10, ds=LOKI, options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"})
panel("logs", "Consumer, exporter and errors",
      [{"datasource": LOKI, "expr": '{service=~".+"} | json | service=~"consumer|exporter" or level="error"', "refId": "A"}],
      12, 12, h=10, ds=LOKI, options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"})

dash = {"uid": "policyground", "title": "PolicyGround", "tags": ["policyground"], "timezone": "utc",
        "schemaVersion": 39, "refresh": "30s", "time": {"from": "now-6h", "to": "now"}, "panels": panels}
out = Path(__file__).parent / "dashboards" / "policyground.json"
out.write_text(json.dumps(dash, indent=2))
print(f"wrote {out} ({len(panels)} panels)")
