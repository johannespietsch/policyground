"""`python -m policyground.seed --tenant T` — generate data/<T>/kg.json, the corpus
snapshot and the golden set through the tenant's adapter (D44).

`--corpus-only` renders another dated snapshot from the existing kg.json, replaying the
recorded render choices so unchanged entities render identically (D38).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from policyground import tenant as tenants
from policyground.render_choices import Chooser


def render_snapshot(data: dict, date: str, root: Path, seed: int = 42, fresh: bool = False) -> dict:
    """Write corpus/<tenant>/<date>/ from kg data through the tenant's adapter; return the manifest."""
    name = data["tenant"]
    choices_path = root / "data" / name / "render-choices.json"
    if fresh or not choices_path.exists():
        ch = Chooser(rng=random.Random(f"{seed}-render"))
    else:
        ch = Chooser(saved=json.loads(choices_path.read_text()), seed=seed)
    docs, manifest = tenants.adapter(name).render(data, ch)
    corpus_dir = root / "corpus" / name / date
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for doc_id, text in docs.items():
        (corpus_dir / f"{doc_id}.md").write_text(text)
    (root / "data" / name / f"manifest-{date}.json").write_text(json.dumps(manifest, indent=2))
    choices_path.write_text(json.dumps(ch.saved, indent=1, sort_keys=True))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date", default="2026-10-16", help="snapshot date (YYYY-MM-DD)")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--corpus-only", action="store_true")
    args = ap.parse_args()

    tenants.spec(args.tenant)  # validate the spec before writing anything
    data_dir = args.root / "data" / args.tenant
    kg_path = data_dir / "kg.json"
    if args.corpus_only:
        data = json.loads(kg_path.read_text())
    else:
        data = tenants.adapter(args.tenant).generate(args.seed, args.date)
        data_dir.mkdir(parents=True, exist_ok=True)
        kg_path.write_text(json.dumps(data, indent=2))

    manifest = render_snapshot(data, args.date, args.root, args.seed, fresh=not args.corpus_only)
    if args.corpus_only:
        print(f"wrote snapshot corpus/{args.tenant}/{args.date} from existing {kg_path}")
        return

    golden = tenants.adapter(args.tenant).golden(data, manifest, args.seed)
    (data_dir / "golden.json").write_text(json.dumps(golden, indent=2))
    print(f"wrote {kg_path} ({len(data['policy_facts'])} facts, {len(data['entities'])} entities), "
          f"corpus/{args.tenant}/{args.date}, {len(golden)} golden questions")


if __name__ == "__main__":
    main()
