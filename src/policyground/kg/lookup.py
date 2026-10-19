"""KG reads for the answer graph, as api_ro: fuzzy property matching (D22) and
resolved policy facts with citable IDs."""

from __future__ import annotations

from dataclasses import dataclass, field

from policyground.db import connect

# Tuned on 30 exact-name questions plus 5 hand probes (D22). Held-out check: Q31-Q35.
MATCH_MIN_SCORE = 0.60
MATCH_MIN_GAP = 0.05


@dataclass
class Match:
    property_id: str | None
    candidates: list[tuple[str, str, float]] = field(default_factory=list)  # (id, name, score)
    reason: str = ""


def match_property(tenant: str, question: str) -> Match:
    """word_similarity scores each name against its best-matching span of the question,
    so a long question doesn't dilute the score."""
    with connect("api_ro") as conn:
        top = conn.execute(
            """SELECT id, name, word_similarity(name, %s) AS score FROM entity
               WHERE tenant = %s AND type = 'property'
               ORDER BY score DESC, id LIMIT 3""",
            (question, tenant),
        ).fetchall()
    best = top[0][2] if top else 0.0
    second = top[1][2] if len(top) > 1 else 0.0
    if best < MATCH_MIN_SCORE:
        return Match(None, top, f"no property name matches well enough (best {best:.2f})")
    if best - second < MATCH_MIN_GAP:
        return Match(None, top, f"ambiguous between {top[0][1]} and {top[1][1]}")
    return Match(top[0][0], top, "")


@dataclass
class Fact:
    fact_id: str      # kg:<entity_id>:<key>, citable
    entity_id: str    # property or rate plan the fact applies to
    key: str
    value: object
    source_type: str  # level it was inherited from
    source_id: str


def property_context(tenant: str, property_id: str) -> tuple[str, list[Fact], list[str]]:
    """(property name, facts for the property and each rate plan, lineage doc IDs)."""
    with connect("api_ro") as conn:
        name, brand_id, chain_id = conn.execute(
            """SELECT p.name, b.id, b.parent_id FROM entity p
               JOIN entity b ON b.tenant = p.tenant AND b.id = p.parent_id
               WHERE p.tenant = %s AND p.id = %s""", (tenant, property_id)).fetchone()
        plans = conn.execute(
            """SELECT id, attrs->>'kind' FROM entity
               WHERE tenant = %s AND parent_id = %s AND type = 'rate_plan' ORDER BY id""",
            (tenant, property_id)).fetchall()
        facts = []
        for entity_id in [property_id] + [pid for pid, _ in plans]:
            for key, value, source_id, source_type, _ in conn.execute(
                    "SELECT * FROM resolve_policy(%s, %s)", (tenant, entity_id)):
                # Rate plans repeat every inherited property fact; keep only their own.
                if entity_id != property_id and source_type != "rate_plan":
                    continue
                facts.append(Fact(f"kg:{entity_id}:{key}", entity_id, key, value, source_type, source_id))
        for plan_id, kind in plans:
            facts.append(Fact(f"kg:{plan_id}:kind", plan_id, "kind", kind, "rate_plan", plan_id))
    return name, facts, [property_id, f"brand-{brand_id}", f"chain-{chain_id}"]
