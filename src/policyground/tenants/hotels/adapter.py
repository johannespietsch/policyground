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


# --- optional hooks for the retrieval eval (policyground.eval.retrieval)

def evidence_text(q: dict, data: dict) -> str | None:
    """Text a chunk must contain to carry the answer (hotel golden items predate
    the generic `evidence_text` field)."""
    from policyground.tenants.hotels.render import FEE_TEXT
    pol = _kg(data).resolve("property", q["property_id"])
    kind, value = q["expected"]["kind"], q["expected"]["value"]
    if kind == "no_free_cancellation":
        return "non-refundable"
    if kind in ("datetime", "no_charge"):
        return f"{pol['cancel_window_hours']['value']} hours"
    if kind == "time":
        return value
    if kind == "eur":
        return f"EUR {value}"
    if kind == "fee":
        return FEE_TEXT[value]
    return None


def rule_and_exception(q: dict, data: dict, root) -> tuple[str, str] | None:
    """For non-refundable questions whose property doc states the rule itself: the rule
    text and the exception text that should share one chunk (M2 "NR together")."""
    from pathlib import Path
    if q["expected"]["kind"] != "no_free_cancellation":
        return None
    kg = _kg(data)
    manifest = json.loads((Path(root) / f"data/hotels/manifest-{kg.snapshot_date}.json").read_text())
    if manifest[q["property_id"]]["cancel_by_reference"]:
        return None
    return f"{kg.resolve('property', q['property_id'])['cancel_window_hours']['value']} hours", "non-refundable"
