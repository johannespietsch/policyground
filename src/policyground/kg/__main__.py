"""`python -m policyground.kg --tenant T` — load data/<T>/kg.json into the KG tables, as
ingest_rw. Generic over tenants (D44): entity types and their order come from the spec.

Upserts, so re-running is safe; fact writes are version-guarded like the stream consumer
(D34), so a bulk reload can never roll back a newer value. Entities are inserted in level
order so the parent foreign key holds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from psycopg.types.json import Jsonb

from policyground import tenant as tenants
from policyground.db import connect


def validate(data: dict, spec: tenants.Spec) -> None:
    ids = {e["id"]: e for e in data["entities"]}
    for e in data["entities"]:
        if e["type"] not in spec.levels:
            raise tenants.SpecError(f"entity {e['id']}: type {e['type']!r} not in levels {spec.levels}")
        want = spec.parent_level(e["type"])
        got = ids[e["parent_id"]]["type"] if e["parent_id"] in ids else None
        if e["parent_id"] and e["parent_id"] not in ids:
            raise tenants.SpecError(f"entity {e['id']}: parent {e['parent_id']} does not exist")
        if got != want:
            raise tenants.SpecError(f"entity {e['id']} ({e['type']}): parent must be a {want}, got {got}")
    for f in data["policy_facts"]:
        if f["entity_id"] not in ids:
            raise tenants.SpecError(f"fact {f['key']}: unknown entity {f['entity_id']}")
        if f["key"] not in spec.facts:
            raise tenants.SpecError(f"fact key {f['key']!r} is not declared in spec.yaml facts")


def load(data: dict) -> tuple[int, int]:
    spec = tenants.spec(data["tenant"])
    validate(data, spec)
    order = {lvl: i for i, lvl in enumerate(spec.levels)}
    entities = sorted(data["entities"], key=lambda e: order[e["type"]])
    with connect("ingest_rw") as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO entity (tenant, id, type, parent_id, name, attrs)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (tenant, id) DO UPDATE
               SET type = EXCLUDED.type, parent_id = EXCLUDED.parent_id,
                   name = EXCLUDED.name, attrs = EXCLUDED.attrs""",
            [(data["tenant"], e["id"], e["type"], e["parent_id"], e.get("name"), Jsonb(e.get("attrs") or {}))
             for e in entities],
        )
        cur.executemany(
            """INSERT INTO policy_fact (tenant, entity_id, key, value, valid_from, version)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (tenant, entity_id, key) DO UPDATE
               SET value = EXCLUDED.value, valid_from = EXCLUDED.valid_from,
                   version = EXCLUDED.version, updated_at = now()
               WHERE EXCLUDED.version > policy_fact.version""",
            [(data["tenant"], f["entity_id"], f["key"], Jsonb(f["value"]), f["valid_from"], f.get("version", 1))
             for f in data["policy_facts"]],
        )
    return len(entities), len(data["policy_facts"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()
    data = json.loads((args.root / "data" / args.tenant / "kg.json").read_text())
    n_entities, n_facts = load(data)
    print(f"loaded {n_entities} entities and {n_facts} policy facts into the {args.tenant} KG")


if __name__ == "__main__":
    main()
