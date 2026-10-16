"""Knowledge-graph model and the reference policy resolver.

Hierarchy: chain -> brand -> property -> rate_plan. Every policy value is a
`policy_fact` attached to one entity; the most specific level wins (D11).

This Python resolver is the ground truth for golden answers. The M2 SQL
resolver (recursive CTE) must agree with it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

LEVELS = ("chain", "brand", "property", "rate_plan")


@dataclass
class PolicyFact:
    entity_type: str  # one of LEVELS
    entity_id: str
    key: str
    value: str | int | bool
    valid_from: str  # ISO date


@dataclass
class KG:
    tenant: str
    seed: int
    snapshot_date: str
    chains: list[dict] = field(default_factory=list)
    brands: list[dict] = field(default_factory=list)
    properties: list[dict] = field(default_factory=list)
    rate_plans: list[dict] = field(default_factory=list)
    policy_facts: list[PolicyFact] = field(default_factory=list)

    def parent_of(self, entity_type: str, entity_id: str) -> tuple[str, str] | None:
        if entity_type == "rate_plan":
            return "property", self._by_id("rate_plans", entity_id)["property_id"]
        if entity_type == "property":
            return "brand", self._by_id("properties", entity_id)["brand_id"]
        if entity_type == "brand":
            return "chain", self._by_id("brands", entity_id)["chain_id"]
        return None

    def lineage(self, entity_type: str, entity_id: str) -> list[tuple[str, str]]:
        """Most general first: [(chain, id), (brand, id), ...]."""
        path = [(entity_type, entity_id)]
        while (parent := self.parent_of(*path[-1])) is not None:
            path.append(parent)
        return list(reversed(path))

    def resolve(self, entity_type: str, entity_id: str) -> dict[str, dict]:
        """Effective policy for an entity: {key: {value, source_type, source_id}}.

        Walks chain -> ... -> entity, letting each more specific level overwrite.
        """
        facts = self._facts_index()
        effective: dict[str, dict] = {}
        for level_type, level_id in self.lineage(entity_type, entity_id):
            for f in facts.get((level_type, level_id), []):
                effective[f.key] = {
                    "value": f.value,
                    "source_type": level_type,
                    "source_id": level_id,
                }
        return effective

    def _by_id(self, collection: str, entity_id: str) -> dict:
        index = self.__dict__.setdefault(f"_idx_{collection}", None)
        if index is None:
            index = {e["id"]: e for e in getattr(self, collection)}
            self.__dict__[f"_idx_{collection}"] = index
        return index[entity_id]

    def _facts_index(self) -> dict[tuple[str, str], list[PolicyFact]]:
        index: dict[tuple[str, str], list[PolicyFact]] = {}
        for f in self.policy_facts:
            index.setdefault((f.entity_type, f.entity_id), []).append(f)
        return index

    def to_json(self) -> str:
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_idx_")}
        return json.dumps(data, indent=2)

    @classmethod
    def load(cls, path: Path) -> KG:
        data = json.loads(path.read_text())
        data["policy_facts"] = [PolicyFact(**f) for f in data["policy_facts"]]
        return cls(**data)
