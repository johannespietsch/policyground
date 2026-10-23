"""`python -m policyground.kg` — load data/<tenant>/kg.json into the KG tables, as ingest_rw.

Upserts, so re-running is safe. Entities are inserted parents-first so the
parent foreign key holds.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from psycopg.types.json import Jsonb

from policyground.db import connect
from policyground.seed.kg import KG


def load(kg: KG) -> tuple[int, int]:
    entities = (
        [(c["id"], "chain", None, c["name"], {}) for c in kg.chains]
        + [(b["id"], "brand", b["chain_id"], b["name"], {}) for b in kg.brands]
        + [(p["id"], "property", p["brand_id"], p["name"], {"city": p["city"]}) for p in kg.properties]
        + [(r["id"], "rate_plan", r["property_id"], None, {"kind": r["kind"]}) for r in kg.rate_plans]
    )
    with connect("ingest_rw") as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO entity (tenant, id, type, parent_id, name, attrs)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (tenant, id) DO UPDATE
               SET type = EXCLUDED.type, parent_id = EXCLUDED.parent_id,
                   name = EXCLUDED.name, attrs = EXCLUDED.attrs""",
            [(kg.tenant, i, t, parent, name, Jsonb(attrs)) for i, t, parent, name, attrs in entities],
        )
        # Version-guarded like the stream consumer (D34): a bulk reload of an older
        # kg.json can never roll back a newer value that arrived as an event.
        cur.executemany(
            """INSERT INTO policy_fact (tenant, entity_id, key, value, valid_from, version)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (tenant, entity_id, key) DO UPDATE
               SET value = EXCLUDED.value, valid_from = EXCLUDED.valid_from,
                   version = EXCLUDED.version, updated_at = now()
               WHERE EXCLUDED.version > policy_fact.version""",
            [(kg.tenant, f.entity_id, f.key, Jsonb(f.value), f.valid_from, f.version)
             for f in kg.policy_facts],
        )
    return len(entities), len(kg.policy_facts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()
    n_entities, n_facts = load(KG.load(args.root / "data" / args.tenant / "kg.json"))
    print(f"loaded {n_entities} entities and {n_facts} policy facts into the KG")


if __name__ == "__main__":
    main()
