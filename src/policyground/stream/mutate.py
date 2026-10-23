"""`python -m policyground.stream.mutate --date D` — the simulated partner system changes
policies (PLAN M4, D33).

1. Changes ~10% of properties in the partner's state (data/<tenant>/kg.json): their
   cancellation window or pet fee, as a property-level fact with version + 1.
2. Writes the snapshot for D from the new state (what the nightly DAG will ingest).
3. Re-derives the golden set's expected answers from the new truth, and writes a
   probe set about exactly the mutated properties, with old and new answers (D35).
4. Publishes one policy.changed event per changed fact, keyed by property_id.

Trap-demo flags (PLAN M4): --no-key publishes without a key (round-robin
partitions, so no per-property order); --replay-stale also re-sends each change's
previous version afterwards, as a broker re-delivery or a late producer would.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from confluent_kafka import Producer

from policyground.eval.golden import _deadline, add_governing, refresh_expected
from policyground.seed.__main__ import render_snapshot
from policyground.seed.generate import CANCEL_WINDOWS, PET_FEES_EUR
from policyground.seed.kg import KG, PolicyFact
from policyground.stream.events import BOOTSTRAP, TOPIC, PolicyChanged

P_WINDOW_CHANGE = 0.7  # otherwise the pet fee changes (only where pets are allowed)


def mutate(kg: KG, when: str, fraction: float, rng: random.Random) -> list[dict]:
    props = sorted(p["id"] for p in kg.properties)
    changes = []
    for pid in rng.sample(props, round(fraction * len(props))):
        pol = kg.resolve("property", pid)
        if rng.random() < P_WINDOW_CHANGE or not pol["pets_allowed"]["value"]:
            key, choices = "cancel_window_hours", CANCEL_WINDOWS
        else:
            key, choices = "pet_fee_eur", PET_FEES_EUR
        old = pol[key]["value"]
        new = rng.choice([c for c in choices if c != old])
        own = next((f for f in kg.policy_facts
                    if f.entity_type == "property" and f.entity_id == pid and f.key == key), None)
        if own:
            own.value, own.version, own.valid_from = new, own.version + 1, when
            version = own.version
        else:  # first property-level override of an inherited value
            kg.policy_facts.append(PolicyFact("property", pid, key, new, when, version=1))
            version = 1
        changes.append({"property_id": pid, "key": key, "old": old, "new": new,
                        "version": version, "old_source": pol[key]["source_type"]})
    return changes


def probes(kg: KG, manifest: dict, changes: list[dict], when: str) -> list[dict]:
    names = {p["id"]: p["name"] for p in kg.properties}
    checkin = date.fromisoformat(when) + timedelta(days=30)
    out = []
    for i, c in enumerate(changes, start=1):
        pid = c["property_id"]
        pol = kg.resolve("property", pid)
        if c["key"] == "cancel_window_hours":
            ci = pol["check_in_time"]["value"]
            q = {"question": f"A guest checks in at {names[pid]} on {checkin.isoformat()}. "
                             "Until when can they cancel free of charge?",
                 "type": "probe_cancel_deadline",
                 "expected": {"kind": "datetime", "value": _deadline(checkin, ci, c["new"])},
                 "expected_old": {"kind": "datetime", "value": _deadline(checkin, ci, c["old"])}}
        else:
            q = {"question": f"How much is the pet fee per night at {names[pid]}?",
                 "type": "probe_pet_fee",
                 "expected": {"kind": "eur", "value": c["new"]},
                 "expected_old": {"kind": "eur", "value": c["old"]}}
        q.update({"id": f"P{i:02d}", "property_id": pid, "evidence_docs": [pid]})
        out.append(add_governing(q, kg, manifest))
    return out


def publish(changes: list[dict], tenant: str, when: str, keyed: bool, replay_stale: bool) -> int:
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "enable.idempotence": True})
    events = [PolicyChanged(tenant, "property", c["property_id"], c["key"], c["new"],
                            c["version"], when, c["property_id"]) for c in changes]
    if replay_stale:
        # The previous version, arriving AFTER the new one (re-delivery / late producer).
        events += [PolicyChanged(tenant, "property", c["property_id"], c["key"], c["old"],
                                 c["version"] - 1, when, c["property_id"])
                   for c in changes if c["version"] > 1]
    for e in events:
        producer.produce(TOPIC, key=e.property_id.encode() if keyed else None, value=e.to_bytes())
    producer.flush(10)
    return len(events)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date", required=True, help="effective date of the changes = new snapshot date")
    ap.add_argument("--fraction", type=float, default=0.10)
    ap.add_argument("--no-key", action="store_true", help="TRAP DEMO: no partition key")
    ap.add_argument("--replay-stale", action="store_true", help="TRAP DEMO: re-send old versions")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()

    data = args.root / "data" / args.tenant
    kg = KG.load(data / "kg.json")
    changes = mutate(kg, args.date, args.fraction, random.Random(f"mutate-{args.date}"))
    (data / "kg.json").write_text(kg.to_json())
    manifest = render_snapshot(kg, args.date, args.root, kg.seed)

    golden = json.loads((data / "golden.json").read_text())
    touched = {c["property_id"] for c in changes}
    golden = [refresh_expected(q, kg, manifest) if q.get("property_id") in touched else q for q in golden]
    (data / "golden.json").write_text(json.dumps(golden, indent=2))

    (data / "mutations").mkdir(exist_ok=True)
    (data / "mutations" / f"{args.date}.json").write_text(json.dumps(changes, indent=2))
    (data / f"probes-{args.date}.json").write_text(json.dumps(probes(kg, manifest, changes, args.date), indent=2))

    n = publish(changes, args.tenant, args.date, keyed=not args.no_key, replay_stale=args.replay_stale)
    print(f"mutate {args.date}: {len(changes)} changes ({sum(c['key'] == 'cancel_window_hours' for c in changes)} "
          f"windows, {sum(c['key'] == 'pet_fee_eur' for c in changes)} pet fees); "
          f"{len(touched & {q.get('property_id') for q in golden})} golden properties touched; "
          f"published {n} events{' WITHOUT keys' if args.no_key else ''}"
          f"{' incl. stale replays' if args.replay_stale else ''}")


if __name__ == "__main__":
    main()
