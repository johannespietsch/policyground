"""Hotels adapter (D44): the three code hooks the core calls. The hotel generator,
renderer and golden-set builder live next to this file, unchanged from M1-M4."""

from __future__ import annotations

import json

from policyground.render_choices import Chooser
from policyground.tenants.hotels.generate import generate as _generate
from policyground.tenants.hotels.golden import add_governing, build, build_fuzzy, build_hard
from policyground.tenants.hotels.kg import KG, PolicyFact
from policyground.tenants.hotels.render import render_brand, render_chain, render_property


def _kg(data: dict) -> KG:
    d = {k: v for k, v in data.items() if k != "entities"}
    d["policy_facts"] = [PolicyFact(**f) for f in d["policy_facts"]]
    return KG(**d)


def generate(seed: int, snapshot_date: str) -> dict:
    """-> kg.json content: generic `entities` + `policy_facts` (plus hotel-only fields)."""
    return json.loads(_generate(seed=seed, tenant="hotels", snapshot_date=snapshot_date).to_json())


def render(data: dict, chooser: Chooser) -> tuple[dict[str, str], dict]:
    """-> ({doc_id: markdown}, manifest). The chooser records/replays every random choice (D38)."""
    kg = _kg(data)
    docs = {f"chain-{c['id']}": render_chain(kg, c["id"], chooser) for c in kg.chains}
    docs |= {f"brand-{b['id']}": render_brand(kg, b["id"], chooser) for b in kg.brands}
    manifest = {}
    for p in kg.properties:
        docs[p["id"]], manifest[p["id"]] = render_property(kg, p["id"], chooser)
    return docs, manifest


def golden(data: dict, manifest: dict, seed: int) -> list[dict]:
    kg = _kg(data)
    qs = build(kg, manifest, seed=seed)
    fuzzy = build_fuzzy(kg, {q["property_id"] for q in qs}, seed=seed)
    qs += [{"id": f"Q{len(qs) + i:02d}", **q} for i, q in enumerate(fuzzy, start=1)]
    hard = build_hard(kg, {q["property_id"] for q in qs if q["property_id"]}, seed=seed)
    qs += [{"id": f"Q{len(qs) + i:02d}", **q} for i, q in enumerate(hard, start=1)]
    return [add_governing(q, kg, manifest) for q in qs]
