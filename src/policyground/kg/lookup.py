"""KG reads for the answer graph, as api_ro: fuzzy subject matching (D22) and resolved
policy facts with citable IDs. Generic over tenants (D44): the matched level, variant
level and document naming come from the tenant spec."""

from __future__ import annotations

from dataclasses import dataclass, field

from policyground import tenant as tenants
from policyground.db import connect

# Tuned on 30 exact-name questions plus 5 hand probes (D22). Held-out check: Q31-Q35.
MATCH_MIN_SCORE = 0.60
MATCH_MIN_GAP = 0.05


@dataclass
class Match:
    subject_id: str | None
    candidates: list[tuple[str, str, float]] = field(default_factory=list)  # (id, name, score)
    reason: str = ""


def match_subject(tenant: str, question: str) -> Match:
    """word_similarity scores each name against its best-matching span of the question,
    so a long question doesn't dilute the score."""
    level = tenants.spec(tenant).subject
    with connect("api_ro") as conn:
        top = conn.execute(
            """SELECT id, name, word_similarity(name, %s) AS score FROM entity
               WHERE tenant = %s AND type = %s
               ORDER BY score DESC, id LIMIT 3""",
            (question, tenant, level),
        ).fetchall()
    best = top[0][2] if top else 0.0
    second = top[1][2] if len(top) > 1 else 0.0
    noun = tenants.spec(tenant).prompt.get("subject_noun", level)
    if best < MATCH_MIN_SCORE:
        return Match(None, top, f"no {noun} name matches well enough (best {best:.2f})")
    if best - second < MATCH_MIN_GAP:
        return Match(None, top, f"ambiguous between {top[0][1]} and {top[1][1]}")
    return Match(top[0][0], top, "")


@dataclass
class Fact:
    fact_id: str      # kg:<entity_id>:<key>, citable
    entity_id: str    # the subject or one of its variants
    key: str
    value: object
    source_type: str  # level it was inherited from
    source_id: str


def subject_context(tenant: str, subject_id: str) -> tuple[str, list[Fact], list[str]]:
    """(subject name, facts for the subject and each variant, lineage doc IDs)."""
    spec = tenants.spec(tenant)
    with connect("api_ro") as conn:
        lineage = conn.execute(
            """WITH RECURSIVE up AS (
                   SELECT id, type, parent_id, name, 0 AS depth FROM entity WHERE tenant = %s AND id = %s
                 UNION ALL
                   SELECT e.id, e.type, e.parent_id, e.name, up.depth + 1 FROM entity e
                   JOIN up ON e.tenant = %s AND e.id = up.parent_id WHERE up.depth < 10)
               SELECT id, type, name FROM up ORDER BY depth""",
            (tenant, subject_id, tenant)).fetchall()
        variants = conn.execute(
            """SELECT id, attrs FROM entity WHERE tenant = %s AND parent_id = %s AND type = %s ORDER BY id""",
            (tenant, subject_id, spec.variant)).fetchall() if spec.variant else []
        facts = []
        for entity_id in [subject_id] + [vid for vid, _ in variants]:
            for key, value, source_id, source_type, _ in conn.execute(
                    "SELECT * FROM resolve_policy(%s, %s)", (tenant, entity_id)):
                # Variants repeat every inherited subject fact; keep only their own.
                if entity_id != subject_id and source_type != spec.variant:
                    continue
                facts.append(Fact(f"kg:{entity_id}:{key}", entity_id, key, value, source_type, source_id))
        for vid, attrs in variants:  # e.g. a rate plan's kind: shown as a citable fact
            for k, v in (attrs or {}).items():
                facts.append(Fact(f"kg:{vid}:{k}", vid, k, v, spec.variant, vid))
    name = lineage[0][2]
    docs = [spec.doc_id({"id": eid, "type": etype}) for eid, etype, _ in lineage]
    return name, facts, docs
