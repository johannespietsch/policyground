"""`python -m policyground.stream.consumer` — apply policy.changed events to the KG.

    poll -> write (one transaction, as ingest_rw) -> commit the Kafka offset

The offset is committed only after the database commit, so a crash between the two
re-delivers the event rather than losing it (at-least-once). Re-delivery is
harmless because the write is version-guarded (D34): it applies only if the event's
version is newer than the stored one, so duplicates and late, older events are
ignored.

--no-guard turns the guard off. It exists ONLY to demonstrate the PLAN M4 trap
(an older event overwriting a newer value); never use it otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from confluent_kafka import Consumer, KafkaError, TopicPartition
from prometheus_client import start_http_server
from psycopg.types.json import Jsonb

from policyground.db import connect
from policyground.obs import logs, metrics
from policyground.stream.events import BOOTSTRAP, TOPIC, PolicyChanged

METRICS_PORT = 8001


def _update_lag(consumer: Consumer) -> None:
    """Lag per partition = high watermark - our position (events not yet consumed)."""
    for tp in consumer.assignment():
        _, high = consumer.get_watermark_offsets(tp, cached=False, timeout=2)
        [pos] = consumer.position([TopicPartition(tp.topic, tp.partition)])
        current = pos.offset if pos.offset >= 0 else 0
        metrics.CONSUMER_LAG.labels(str(tp.partition)).set(max(high - current, 0))

GUARDED = """
    INSERT INTO policy_fact (tenant, entity_id, key, value, valid_from, version, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, now())
    ON CONFLICT (tenant, entity_id, key) DO UPDATE
    SET value = EXCLUDED.value, valid_from = EXCLUDED.valid_from,
        version = EXCLUDED.version, updated_at = now()
    WHERE EXCLUDED.version > policy_fact.version"""

# Last-write-wins: what a consumer looks like without the guard (trap demo only).
UNGUARDED = GUARDED.replace("\n    WHERE EXCLUDED.version > policy_fact.version", "")


def apply(conn, e: PolicyChanged, guard: bool = True) -> bool:
    """True if the KG changed."""
    cur = conn.execute(GUARDED if guard else UNGUARDED,
                       (e.tenant, e.entity_id, e.key, Jsonb(e.value), e.valid_from, e.version))
    return cur.rowcount == 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="policyground-kg")
    ap.add_argument("--idle-exit", type=float, default=0,
                    help="exit after this many seconds without messages (0 = run forever)")
    ap.add_argument("--no-guard", action="store_true", help="TRAP DEMO ONLY: last write wins")
    ap.add_argument("--metrics-port", type=int, default=METRICS_PORT, help="0 = no /metrics")
    args = ap.parse_args()
    log = logs.setup("consumer")
    if args.metrics_port:
        start_http_server(args.metrics_port)

    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": args.group,
        "enable.auto.commit": False,      # we commit after the DB write, never before
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([TOPIC])
    counts = {"applied": 0, "ignored": 0}
    last_message = last_lag = time.monotonic()
    with connect("ingest_rw") as conn:
        conn.autocommit = False
        try:
            while True:
                msg = consumer.poll(1.0)
                if time.monotonic() - last_lag > 5:
                    _update_lag(consumer)
                    last_lag = time.monotonic()
                if msg is None:
                    if args.idle_exit and time.monotonic() - last_message > args.idle_exit:
                        break
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        print(json.dumps({"error": str(msg.error())}), file=sys.stderr, flush=True)
                    continue
                last_message = time.monotonic()
                e = PolicyChanged.from_bytes(msg.value())
                changed = apply(conn, e, guard=not args.no_guard)
                conn.commit()                                  # 1. the KG write is durable
                consumer.commit(message=msg, asynchronous=False)  # 2. only then move the offset
                outcome = "applied" if changed else "ignored"
                counts[outcome] += 1
                metrics.EVENTS.labels(outcome).inc()
                if changed:
                    metrics.LAST_APPLIED.set_to_current_time()
                fields = {"partition": msg.partition(), "offset": msg.offset(), "entity": e.entity_id,
                          "key": e.key, "version": e.version, "value": e.value, "applied": changed,
                          "event_id": e.event_id}
                logs.event(log, "policy.changed", **fields)
                print(json.dumps(fields), flush=True)
        finally:
            consumer.close()
    print(json.dumps({"summary": counts, "guard": not args.no_guard}), flush=True)


if __name__ == "__main__":
    main()
