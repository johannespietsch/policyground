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
from policyground.eval.score import is_correct  # noqa: E402
from policyground.llm import MODEL, PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK  # noqa: E402

MILESTONE = "M1"
CHUNKER, EMBEDDER = "naive-800", "bge-small-en-v1.5"


def git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()

    golden = json.loads((args.root / "data" / args.tenant / "golden.json").read_text())
    graph = graph_mod.build()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    results = []
    for q in golden:
        t0 = time.perf_counter()
        state = graph.invoke({"tenant": args.tenant, "question": q["question"]})
        latency = time.perf_counter() - t0
        retrieved_docs = [c["id"].split("#")[0] for c in state["chunks"]]
        results.append({
            "id": q["id"], "type": q["type"], "question": q["question"], "expected": q["expected"],
            "answer": state["answer"], "abstain": state["abstain"], "citations": state["citations"],
            "retrieved": [c["id"] for c in state["chunks"]],
            "evidence_docs": q["evidence_docs"],
            "hit5": all(d in retrieved_docs for d in q["evidence_docs"]) if q["evidence_docs"] else None,
            "correct": is_correct(q["expected"], state["answer"], state["abstain"]),
            "input_tokens": state["input_tokens"], "output_tokens": state["output_tokens"],
            "cost_usd": (state["input_tokens"] * PRICE_IN_PER_MTOK
                         + state["output_tokens"] * PRICE_OUT_PER_MTOK) / 1e6,
            "latency_s": latency,
        })
        print(f"{q['id']} {'✓' if results[-1]['correct'] else '✗'} {q['type']}", flush=True)

    answerable = [r for r in results if r["expected"]["kind"] != "abstain"]
    unanswerable = [r for r in results if r["expected"]["kind"] == "abstain"]
    lat = sorted(r["latency_s"] for r in results)
    summary = {
        "correct": sum(r["correct"] for r in answerable) / len(answerable),
        "abst_acc": sum(r["abstain"] for r in unanswerable) / len(unanswerable),
        "false_abst": sum(r["abstain"] for r in answerable) / len(answerable),
        "hit5": sum(r["hit5"] for r in answerable) / len(answerable),
        "cost_per_q": statistics.mean(r["cost_usd"] for r in results),
        "p50_s": statistics.median(lat),
        "p95_s": lat[min(len(lat) - 1, round(0.95 * (len(lat) - 1)))],
    }
    by_type = defaultdict(lambda: [0, 0, 0])
    for r in results:
        t = by_type[r["type"].rsplit("_", 0)[0]]
        t[0] += r["correct"]; t[1] += 1; t[2] += bool(r["hit5"])

    out = args.root / "data" / args.tenant / "eval" / f"run-{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"run": run_id, "commit": git_sha(), "milestone": MILESTONE, "tenant": args.tenant,
            "chunker": CHUNKER, "embedder": EMBEDDER, "model": MODEL, "n": len(results)}
    out.write_text(json.dumps({**meta, "summary": summary, "results": results}, indent=2))

    s = summary
    row = (f"| {run_id} | {meta['commit']} | {MILESTONE} | {args.tenant} | {CHUNKER} | {EMBEDDER} | {MODEL} "
           f"| {len(results)} | {s['correct']:.2f} | {s['abst_acc']:.2f} | {s['false_abst']:.2f} "
           f"| {s['hit5']:.2f} | {s['cost_per_q']:.5f} | {s['p50_s']:.1f} | {s['p95_s']:.1f} |\n")
    with open(args.root / "METRICS.md", "a") as f:
        f.write(row)

    print(f"\ncorrect {s['correct']:.2f}  abst-acc {s['abst_acc']:.2f}  false-abst {s['false_abst']:.2f}  "
          f"hit@5 {s['hit5']:.2f}  $/q {s['cost_per_q']:.5f}  p50 {s['p50_s']:.1f}s  p95 {s['p95_s']:.1f}s")
    print("by type (correct/n, hit@5):")
    for t, (c, n, h) in sorted(by_type.items()):
        print(f"  {t:34s} {c}/{n}  hit {h}/{n}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
