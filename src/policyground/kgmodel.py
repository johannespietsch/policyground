"""Tenant-independent knowledge-graph model (D44).

kg.json (every tenant) = {"tenant", "seed", "snapshot_date", "entities": [...], "policy_facts": [...]}
  entity:  {"id", "type", "parent_id", "name", "attrs"}   type is one of the spec's levels
  fact:    {"entity_type", "entity_id", "key", "value", "valid_from", "version"}

`resolve` is the reference resolver (most specific level wins); the SQL function
resolve_policy must agree with it (tests/test_kg_sql.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GenericKG:
    tenant: str
    entities: list[dict]
    policy_facts: list[dict]
    seed: int = 0
    snapshot_date: str = ""
    by_id: dict = field(init=False, repr=False)

    def __post_init__(self):
        self.by_id = {e["id"]: e for e in self.entities}

    def lineage(self, entity_id: str) -> list[dict]:
        """Root first: [root, ..., entity]."""
        path, cur = [], self.by_id[entity_id]
        while cur is not None:
            path.append(cur)
            cur = self.by_id.get(cur["parent_id"]) if cur["parent_id"] else None
        return list(reversed(path))

    def children(self, entity_id: str) -> list[dict]:
        return [e for e in self.entities if e["parent_id"] == entity_id]

    def resolve(self, entity_id: str) -> dict[str, dict]:
        index: dict[str, list[dict]] = {}
        for f in self.policy_facts:
            index.setdefault(f["entity_id"], []).append(f)
        out = {}
        for e in self.lineage(entity_id):
            for f in index.get(e["id"], []):
                out[f["key"]] = {"value": f["value"], "source_type": e["type"], "source_id": e["id"]}
        return out

    @classmethod
    def load(cls, path: Path) -> GenericKG:
        d = json.loads(path.read_text())
        return cls(tenant=d["tenant"], entities=d["entities"], policy_facts=d["policy_facts"],
                   seed=d.get("seed", 0), snapshot_date=d.get("snapshot_date", ""))
