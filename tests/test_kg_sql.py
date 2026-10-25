"""The SQL resolver (recursive CTE) must agree with the Python resolver that
produced the golden answers, for every property and rate plan."""

from pathlib import Path

import psycopg
import pytest

from policyground.db import connect
from policyground.tenants.hotels.kg import KG

KG_PATH = Path("data/hotels/kg.json")

try:
    connect("api_ro").close()
except psycopg.OperationalError:
    pytest.skip("postgres not running (make up)", allow_module_level=True)
if not KG_PATH.exists():
    pytest.skip("no kg.json (make seed)", allow_module_level=True)


def test_sql_resolver_matches_python():
    kg = KG.load(KG_PATH)
    targets = [("property", p["id"]) for p in kg.properties] + [("rate_plan", r["id"]) for r in kg.rate_plans]
    mismatches = []
    with connect("api_ro") as conn:
        for etype, eid in targets:
            sql = {k: {"value": v, "source_type": st, "source_id": sid}
                   for k, v, sid, st, _ in conn.execute(
                       "SELECT key, value, source_id, source_type, depth FROM resolve_policy(%s, %s)",
                       (kg.tenant, eid))}
            if sql != kg.resolve(etype, eid):
                mismatches.append(eid)
    assert not mismatches, f"{len(mismatches)} mismatches, e.g. {mismatches[:5]}"


def test_api_ro_cannot_write_kg():
    with connect("api_ro") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE policy_fact SET value = '0'")
