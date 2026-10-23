"""`python -m policyground.stream.order_demo` — the PLAN M4 out-of-order trap, on an
isolated tenant ("demo-order") so the real KG is never touched (INCIDENTS #9).

1. Stale replay (deterministic): v1, v2, v3, then v2 again, keyed. A last-write-wins
   consumer ends at v2; the version-guarded one stays at v3.
2. No key (non-deterministic): v1..v5 published without a key, so round-robin across
   3 partitions; one consumer reads the partitions in no particular order. Over
   several trials, count how often each consumer ends somewhere other than v5.
"""

from __future__ import annotations

import uuid

from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic

from policyground.db import connect
from policyground.stream.consumer import apply
from policyground.stream.events import BOOTSTRAP, PolicyChanged

TENANT, PID, KEY = "demo-order", "DEMO-P1", "cancel_window_hours"


def setup() -> None:
    with connect("ingest_rw") as conn:
        conn.execute("DELETE FROM policy_fact WHERE tenant = %s", (TENANT,))
        for eid, etype, parent in (("DEMO-C", "chain", None), ("DEMO-B", "brand", "DEMO-C"),
                                   (PID, "property", "DEMO-B")):
            conn.execute("""INSERT INTO entity (tenant, id, type, parent_id) VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING""", (TENANT, eid, etype, parent))


def stored() -> tuple[object, int]:
    with connect("api_ro") as conn:
        return conn.execute("SELECT value, version FROM policy_fact WHERE tenant=%s AND entity_id=%s AND key=%s",
                            (TENANT, PID, KEY)).fetchone()


def run_trial(versions: list[int], keyed: bool, guard: bool) -> tuple[object, int]:
    topic = f"demo.order.{uuid.uuid4().hex[:8]}"
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    admin.create_topics([NewTopic(topic, num_partitions=3, replication_factor=1)])[topic].result()
    producer = Producer({"bootstrap.servers": BOOTSTRAP})
    for v in versions:
        e = PolicyChanged(TENANT, "property", PID, KEY, 24 * v, v, "2026-10-21", PID)
        producer.produce(topic, key=PID.encode() if keyed else None, value=e.to_bytes())
    producer.flush(10)

    setup()
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": topic,
                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    consumer.subscribe([topic])
    seen = 0
    with connect("ingest_rw") as conn:
        while seen < len(versions):
            msg = consumer.poll(5.0)
            if msg is None or msg.error():
                continue
            apply(conn, PolicyChanged.from_bytes(msg.value()), guard=guard)
            conn.commit()
            consumer.commit(message=msg, asynchronous=False)
            seen += 1
    consumer.close()
    admin.delete_topics([topic])
    return stored()


def main() -> None:
    print("1. stale replay, keyed: v1 v2 v3 v2")
    for guard in (False, True):
        value, version = run_trial([1, 2, 3, 2], keyed=True, guard=guard)
        print(f"   guard={guard!s:5}: final version {version} (value {value}) -> "
              f"{'CORRECT' if version == 3 else 'WRONG: an older event overwrote a newer one'}")
    trials = 8
    print(f"2. no key, v1..v5 round-robin over 3 partitions, {trials} trials each")
    for guard in (False, True):
        finals = [run_trial([1, 2, 3, 4, 5], keyed=False, guard=guard)[1] for _ in range(trials)]
        wrong = sum(v != 5 for v in finals)
        print(f"   guard={guard!s:5}: final versions {finals} -> {wrong}/{trials} wrong")
    with connect("ingest_rw") as conn:
        conn.execute("DELETE FROM policy_fact WHERE tenant = %s", (TENANT,))


if __name__ == "__main__":
    main()
