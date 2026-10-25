"""Prometheus metrics (PLAN M5, D40, D41).

Labels come only from ALLOWED_LABELS, all with a small closed set of values. A metric
labelled by property_id would create a series per property x route x outcome, which
grows with the corpus (the PLAN M5 cardinality trap). tests/test_metrics_labels.py
enforces this for every metric defined here.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

ALLOWED_LABELS = {"tenant", "route", "outcome", "reason", "direction", "partition"}

# --- request path (API)
REQUESTS = Counter("policyground_requests_total", "Questions answered by /ask",
                   ["tenant", "route", "outcome"])          # route: kg | unresolved; outcome: answered | abstained | error
LATENCY = Histogram("policyground_request_seconds", "End-to-end /ask latency",
                    ["tenant", "route"], buckets=(0.25, 0.5, 1, 2, 3, 5, 8, 13, 20, 30))
TOKENS = Counter("policyground_llm_tokens_total", "LLM tokens", ["tenant", "direction"])  # in | out
COST = Counter("policyground_llm_cost_usd_total", "LLM cost at list price", ["tenant"])
LLM_CALLS = Counter("policyground_llm_calls_total", "LLM answer calls (incl. regenerates)", ["tenant"])
VALIDATOR_REJECTIONS = Counter("policyground_validator_rejections_total",
                               "Answers rejected by the validator", ["tenant"])
ABSTENTIONS = Counter("policyground_abstentions_total", "Abstentions by reason",
                      ["tenant", "reason"])   # unresolved_property | model | validator | step_limit

# --- stream consumer
EVENTS = Counter("policyground_stream_events_total", "policy.changed events", ["outcome"])  # applied | ignored
CONSUMER_LAG = Gauge("policyground_stream_lag", "Events not yet consumed", ["partition"])
LAST_APPLIED = Gauge("policyground_stream_last_applied_timestamp_seconds", "Last KG change from the stream")

# --- pipeline health (exporter)
DISAGREEMENT = Gauge("policyground_kg_vector_disagreement", "Share of properties where KG and chunks differ",
                     ["tenant"])
SNAPSHOT_AGE = Gauge("policyground_newest_snapshot_age_seconds",
                     "Age of the newest ingested production snapshot (by ingest time)", ["tenant"])
EXPORTER_ERRORS = Counter("policyground_exporter_errors_total", "Failed health computations", ["reason"])


from policyground.tenant import known as _known_tenants

TENANTS = _known_tenants()  # every tenant with a spec.yaml (D44)


def init_series(*names: str) -> None:
    """Create every known label combination at 0 (INCIDENTS #15). A labelled counter only
    appears on its first increment, and Prometheus can't compute increase()/rate() across
    an absent -> N jump, so the first burst after a restart would read as zero."""
    if "api" in names:
        for t in TENANTS:
            for route in ("kg", "unresolved"):
                for outcome in ("answered", "abstained", "error"):
                    REQUESTS.labels(t, route, outcome)
            for reason in ("unresolved_property", "model", "validator", "step_limit"):
                ABSTENTIONS.labels(t, reason)
            for d in ("in", "out"):
                TOKENS.labels(t, d)
            COST.labels(t); LLM_CALLS.labels(t); VALIDATOR_REJECTIONS.labels(t)
    if "consumer" in names:
        for outcome in ("applied", "ignored"):
            EVENTS.labels(outcome)
