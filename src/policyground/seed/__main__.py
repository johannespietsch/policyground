"""`python -m policyground.seed` — write data/<tenant>/kg.json and the corpus snapshot."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from policyground.eval.golden import build as build_golden
from policyground.eval.golden import add_governing, build_fuzzy
from policyground.seed.generate import generate
from policyground.seed.render import render_brand, render_chain, render_property


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date", default="2026-10-16", help="snapshot date (YYYY-MM-DD)")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()

    kg = generate(seed=args.seed, tenant=args.tenant, snapshot_date=args.date)
    kg_path = args.root / "data" / args.tenant / "kg.json"
    kg_path.parent.mkdir(parents=True, exist_ok=True)
    kg_path.write_text(kg.to_json())

    corpus_dir = args.root / "corpus" / args.tenant / args.date
    corpus_dir.mkdir(parents=True, exist_ok=True)
    # Separate RNG stream for wording, so changing templates never changes the KG.
    rng = random.Random(f"{args.seed}-render")
    for chain in kg.chains:
        (corpus_dir / f"chain-{chain['id']}.md").write_text(render_chain(kg, chain["id"], rng))
    for brand in kg.brands:
        (corpus_dir / f"brand-{brand['id']}.md").write_text(render_brand(kg, brand["id"], rng))
    manifest = {}
    for prop in kg.properties:
        doc, manifest[prop["id"]] = render_property(kg, prop["id"], rng)
        (corpus_dir / f"{prop['id']}.md").write_text(doc)
    (kg_path.parent / f"manifest-{args.date}.json").write_text(json.dumps(manifest, indent=2))

    golden = build_golden(kg, manifest, seed=args.seed)
    fuzzy = build_fuzzy(kg, {q["property_id"] for q in golden}, seed=args.seed)
    golden += [{"id": f"Q{len(golden) + i:02d}", **q} for i, q in enumerate(fuzzy, start=1)]
    golden = [add_governing(q, kg) for q in golden]
    (kg_path.parent / "golden.json").write_text(json.dumps(golden, indent=2))

    n_docs = len(kg.chains) + len(kg.brands) + len(kg.properties)
    print(f"wrote {kg_path} ({len(kg.policy_facts)} facts) and {n_docs} docs to {corpus_dir}, "
          f"{len(golden)} golden questions")


if __name__ == "__main__":
    main()
