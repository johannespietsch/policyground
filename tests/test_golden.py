"""The golden set must be answerable from its evidence docs, or the eval is wrong."""

import json
import random

import pytest

from policyground.eval.golden import build
from policyground.seed.generate import generate
from policyground.seed.render import render_brand, render_chain, render_property


@pytest.fixture(scope="module")
def world():
    kg = generate()
    rng = random.Random("42-render")
    docs = {f"chain-{c['id']}": render_chain(kg, c["id"], rng) for c in kg.chains}
    docs |= {f"brand-{b['id']}": render_brand(kg, b["id"], rng) for b in kg.brands}
    manifest = {}
    for p in kg.properties:
        docs[p["id"]], manifest[p["id"]] = render_property(kg, p["id"], rng)
    return kg, docs, build(kg, manifest)


def test_shape(world):
    _, _, golden = world
    kinds = [q["type"].split("_")[0] for q in golden]
    assert (kinds.count("plain"), kinds.count("exception"), kinds.count("unanswerable")) == (20, 5, 5)
    assert len({q["property_id"] for q in golden}) == 30


def test_property_names_are_unique():
    kg = generate()
    assert len({p["name"] for p in kg.properties}) == len(kg.properties)


def test_evidence_docs_contain_the_facts(world):
    kg, docs, golden = world
    for q in golden:
        text = "\n".join(docs[d] for d in q["evidence_docs"])
        pol = kg.resolve("property", q["property_id"])
        if q["expected"]["kind"] == "datetime":
            assert f"{pol['cancel_window_hours']['value']} hours" in text, q["id"]
            assert pol["check_in_time"]["value"] in text, q["id"]
        elif q["expected"]["kind"] in ("time", "eur"):
            assert str(q["expected"]["value"]) in text, q["id"]
        elif q["expected"]["kind"] == "no_free_cancellation":
            assert "non-refundable" in text.lower(), q["id"]


def test_unanswerable_topics_never_appear_in_corpus(world):
    _, docs, golden = world
    corpus = "\n".join(docs.values()).lower()
    for word in ("parking", "shuttle", "minimum age", "city tax", "late check-out"):
        assert word not in corpus, word


def test_governing_doc_states_the_fact():
    """The governing doc must contain the fact text, or 'unsupported' and fact@5 are wrong."""
    from pathlib import Path
    import json as _json
    from policyground.eval.retrieval import surface_text
    from policyground.seed.kg import KG

    if not Path("data/hotels/golden.json").exists():
        pytest.skip("make seed")
    kg = KG.load(Path("data/hotels/kg.json"))
    for q in _json.loads(Path("data/hotels/golden.json").read_text()):
        if q["expected"]["kind"] == "abstain":
            continue
        # Golden answers follow the current truth (D33), stated in the newest snapshot.
        latest = max(Path("corpus/hotels").iterdir())
        text = "\n".join((latest / f"{d}.md").read_text() for d in q["governing"]["docs"])
        assert surface_text(q, kg).lower() in text.lower(), q["id"]
