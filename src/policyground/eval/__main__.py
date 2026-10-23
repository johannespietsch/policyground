"""`python -m policyground.eval` — run the golden set through the graph, score it,
write per-question results and append one row to METRICS.md."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from policyground import graph as graph_mod  # noqa: E402
from policyground.config import BASELINE, PRODUCTION  # noqa: E402
from policyground.eval.metrics_md import append_to_table  # noqa: E402
from policyground.eval.score import is_correct, is_supported  # noqa: E402
from policyground.llm import MODEL, PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK  # noqa: E402

MILESTONE = {"rag": "M1", "kg": "M2"}
RETRIEVAL = {"rag": BASELINE, "kg": PRODUCTION}  # what each graph retrieves with


def git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    # METRICS.md is excluded: the previous eval run's appended row would mark every run dirty.
    dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", ":!METRICS.md"],
                           capture_output=True, text=True).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def _rate(rows, pred) -> float | None:
    return sum(map(pred, rows)) / len(rows) if rows else None


def _fmt(x) -> str:
    return "—" if x is None else f"{x:.2f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--graph", choices=graph_mod.GRAPHS, default="kg")
    args = ap.parse_args()

    golden = json.loads((args.root / "data" / args.tenant / "golden.json").read_text())
    graph = graph_mod.GRAPHS[args.graph]()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    results = []
    for q in golden:
        t0 = time.perf_counter()
        state = graph_mod.ask(graph, args.tenant, q["question"])
        latency = time.perf_counter() - t0
        retrieved_docs = [c["id"].split("#")[0] for c in state["chunks"]]
        results.append({
            "id": q["id"], "type": q["type"], "question": q["question"], "expected": q["expected"],
            "answer": state["answer"], "abstain": state["abstain"], "citations": state["citations"],
            "retrieved": [c["id"] for c in state["chunks"]],
            "evidence_docs": q["evidence_docs"],
            "hit5": all(d in retrieved_docs for d in q["evidence_docs"]) if q["evidence_docs"] else None,
            "correct": is_correct(q["expected"], state["answer"], state["abstain"]),
            "supported": is_supported(q["governing"], state["citations"]),
            "property_id_resolved": state.get("property_id"),
            "attempts": state.get("attempts", 0),
            "validator_problems": state.get("validator_problems") or [],
            "validator_warnings": state.get("validator_warnings") or [],
            "forced_abstain": bool(state.get("forced_abstain")),
            "raw_citations": state.get("raw_citations", []),
            # Kept so the validator can be re-run offline on injected faults (eval/faults.py).
            "facts": state.get("facts", []),
            "chunk_texts": state.get("chunks", []),
            "input_tokens": state["input_tokens"], "output_tokens": state["output_tokens"],
            "cost_usd": (state["input_tokens"] * PRICE_IN_PER_MTOK
                         + state["output_tokens"] * PRICE_OUT_PER_MTOK) / 1e6,
            "latency_s": latency,
        })
        print(f"{q['id']} {'✓' if results[-1]['correct'] else '✗'} {q['type']}", flush=True)

    # Headline metrics use the original 30 only, so rows stay comparable (D22).
    core = [r for r in results if not r["type"].startswith(("fuzzy_", "hard_"))]
    fuzzy = [r for r in results if r["type"].startswith("fuzzy_")]
    hard = [r for r in results if r["type"].startswith("hard_")]
    answerable = [r for r in core if r["expected"]["kind"] != "abstain"]
    unanswerable = [r for r in core if r["expected"]["kind"] == "abstain"]
    lat = sorted(r["latency_s"] for r in results)
    summary = {
        "correct": sum(r["correct"] for r in answerable) / len(answerable),
        "abst_acc": sum(r["abstain"] for r in unanswerable) / len(unanswerable),
        "false_abst": sum(r["abstain"] for r in answerable) / len(answerable),
        "hit5": sum(r["hit5"] for r in answerable) / len(answerable),
        "unsupported": sum(r["correct"] and not r["supported"] for r in answerable) / len(answerable),
        # Over questions that reached the answer node at least once.
        "val_rej": None if args.graph == "rag" else _rate(
            [r for r in core if r["attempts"]], lambda r: bool(r["validator_problems"])),
        "fallback": None if args.graph == "rag" else _rate(
            [r for r in core if r["attempts"]], lambda r: r["attempts"] > 1 or r["forced_abstain"]),
        "fuzzy_correct": sum(r["correct"] for r in fuzzy),
        "fuzzy_n": len(fuzzy),
        "hard_correct": sum(r["correct"] for r in hard),
        "hard_n": len(hard),
        "cost_per_q": statistics.mean(r["cost_usd"] for r in results),
        "p50_s": statistics.median(lat),
        "p95_s": lat[min(len(lat) - 1, round(0.95 * (len(lat) - 1)))],
    }
    by_type = defaultdict(lambda: [0, 0, 0])
    for r in results:
        t = by_type[r["type"]]
        t[0] += r["correct"]; t[1] += 1; t[2] += bool(r["hit5"])

    out = args.root / "data" / args.tenant / "eval" / f"run-{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    ms = MILESTONE[args.graph]
    CHUNKER, EMBEDDER = RETRIEVAL[args.graph]["chunker"], RETRIEVAL[args.graph]["embedder"]
    from policyground.graph import MAX_REGENERATE
    meta = {"max_regenerate": MAX_REGENERATE, "run": run_id, "commit": git_sha(), "milestone": ms, "graph": args.graph, "tenant": args.tenant,
            "chunker": CHUNKER, "embedder": EMBEDDER, "model": MODEL, "n": len(core)}
    out.write_text(json.dumps({**meta, "summary": summary, "results": results}, indent=2))

    s = summary
    fuzzy_cell = f"{s['fuzzy_correct']}/{s['fuzzy_n']}" if fuzzy else "—"
    hard_cell = f"{s['hard_correct']}/{s['hard_n']}" if hard else "—"
    row = (f"| {run_id} | {meta['commit']} | {ms} | {args.tenant} | {CHUNKER} | {EMBEDDER} | {MODEL} "
           f"| {len(core)} | {s['correct']:.2f} | {s['abst_acc']:.2f} | {s['false_abst']:.2f} "
           f"| {s['hit5']:.2f} | {s['cost_per_q']:.5f} | {s['p50_s']:.1f} | {s['p95_s']:.1f} "
           f"| {args.graph} | {s['unsupported']:.2f} | {fuzzy_cell} "
           f"| {_fmt(s['val_rej'])} | {_fmt(s['fallback'])} | {hard_cell} |\n")
    append_to_table(args.root / "METRICS.md", "## Eval runs", row)

    print(f"\ncorrect {s['correct']:.2f}  abst-acc {s['abst_acc']:.2f}  false-abst {s['false_abst']:.2f}  "
          f"hit@5 {s['hit5']:.2f}  unsupported {s['unsupported']:.2f}  fuzzy {fuzzy_cell}  hard {hard_cell}  "
          f"val-rej {_fmt(s['val_rej'])}  fallback {_fmt(s['fallback'])}  $/q {s['cost_per_q']:.5f}  p50 {s['p50_s']:.1f}s  p95 {s['p95_s']:.1f}s")
    print("by type (correct/n, hit@5):")
    for t, (c, n, h) in sorted(by_type.items()):
        no_evidence = all(not r["evidence_docs"] for r in results if r["type"] == t)
        hit = "-" if no_evidence else f"{h}/{n}"  # nothing to retrieve
        print(f"  {t:34s} {c}/{n}  hit {hit}")
    for r in results:
        if not r["correct"] or (r["expected"]["kind"] != "abstain" and not r["supported"]):
            tag = "WRONG" if not r["correct"] else "UNSUPPORTED"
            print(f"  {tag:11s} {r['id']} {r['type']}: {r['answer'][:150]}  cites={r['citations']}")
    for r in results:
        if r["validator_problems"] or r["validator_warnings"]:
            print(f"  VALIDATOR   {r['id']} attempts={r['attempts']} forced_abstain={r['forced_abstain']} "
                  f"problems={r['validator_problems']} warnings={r['validator_warnings']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
