"""`python -m policyground.obs.exporter` — pipeline-health gauges for Prometheus (D40).

Recomputes every INTERVAL seconds:
  policyground_kg_vector_disagreement        share of properties where KG and the newest
                                             production chunks state different values (M4)
  policyground_newest_snapshot_age_seconds   time since the newest production slice was
                                             ingested; also how a skipped nightly DAG run
                                             shows up (no new snapshot)
"""

from __future__ import annotations

import argparse
import time

from prometheus_client import start_http_server

from policyground.config import PRODUCTION
from policyground.db import connect
from policyground.drift import disagreement
from policyground.obs import logs, metrics

INTERVAL = 60


def snapshot_age_seconds(tenant: str) -> float:
    with connect("api_ro") as conn:
        return conn.execute(
            """SELECT extract(epoch FROM now() - max(created_at)) FROM chunks
               WHERE tenant=%s AND chunker=%s AND embedder=%s""",
            (tenant, PRODUCTION["chunker"], PRODUCTION["embedder"])).fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--port", type=int, default=8002)
    ap.add_argument("--interval", type=int, default=INTERVAL)
    args = ap.parse_args()
    log = logs.setup("exporter")
    start_http_server(args.port)
    while True:
        try:
            rate, bad = disagreement(args.tenant)
            metrics.DISAGREEMENT.labels(args.tenant).set(rate)
            age = snapshot_age_seconds(args.tenant)
            metrics.SNAPSHOT_AGE.labels(args.tenant).set(age)
            # Property IDs go to the log, not to a label (D41).
            logs.event(log, "health", tenant=args.tenant, disagreement=rate,
                       disagreeing_properties=bad, snapshot_age_s=round(age))
        except Exception as exc:  # keep exporting; the error counter is itself alertable
            metrics.EXPORTER_ERRORS.labels(type(exc).__name__).inc()
            log.exception("health computation failed")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
