"""`python -m policyground.eval.retry_demo` — INDUCED demonstration of the PLAN M2
retry-cost trap (D23 / INCIDENTS #6).

On real data every validator rejection recovered on the first regenerate, so an
uncapped loop costs nothing extra there. This script induces the failure mode: the
validator is replaced with one that ALWAYS rejects (a persistent false positive),
and one question runs with the retry cap at 1 and then with the cap removed.

With the cap removed, only a recursion limit stops the loop. LangGraph 1.x's default
is 10007 steps, so this demo bounds itself at DEMO_STEPS and projects the rest.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langgraph.errors import GraphRecursionError  # noqa: E402

from policyground import graph as graph_mod  # noqa: E402
from policyground.llm import PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK  # noqa: E402
from policyground.validate import Verdict  # noqa: E402


def always_reject(*_args, **_kwargs) -> Verdict:
    return Verdict(False, ["(induced) persistent validator rejection"])


DEMO_STEPS = 60  # ~28 LLM calls: enough to show the slope, cheap to run


def run(question: str, cap: int, steps: int) -> dict:
    graph_mod.MAX_REGENERATE = cap
    graph_mod.run_validator = always_reject
    g = graph_mod.build_kg()
    calls, in_tok, out_tok, stopped_by = 0, 0, 0, "graph end"
    t0 = time.perf_counter()
    try:
        for update in g.stream({"tenant": "hotels", "question": question}, stream_mode="updates",
                               config={"recursion_limit": steps}):
            if "answer" in update:
                calls += 1
                in_tok, out_tok = update["answer"]["input_tokens"], update["answer"]["output_tokens"]
                print(f"  cap={cap} call {calls}: cumulative {in_tok} in / {out_tok} out, "
                      f"{time.perf_counter() - t0:.1f}s", flush=True)
            if "abstain_unvalidated" in update:
                stopped_by = "retry cap -> abstain"
    except GraphRecursionError:
        stopped_by = f"recursion limit ({steps} steps)"
    cost = (in_tok * PRICE_IN_PER_MTOK + out_tok * PRICE_OUT_PER_MTOK) / 1e6
    return {"cap": cap, "llm_calls": calls, "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": cost, "stopped_by": stopped_by}


def main() -> None:
    q = next(x for x in json.loads(Path("data/hotels/golden.json").read_text()) if x["id"] == "Q01")
    capped = run(q["question"], cap=1, steps=graph_mod.RECURSION_LIMIT)
    uncapped = run(q["question"], cap=10_000, steps=DEMO_STEPS)
    for r in (capped, uncapped):
        print(f"cap={r['cap']:>6}: {r['llm_calls']:2d} LLM calls, {r['input_tokens']:6d} in / "
              f"{r['output_tokens']:5d} out tokens, ${r['cost_usd']:.5f}, stopped by {r['stopped_by']}")
    print(f"uncapped / capped cost after {uncapped['llm_calls']} calls: "
          f"{uncapped['cost_usd'] / capped['cost_usd']:.1f}x")
    per_call = uncapped["cost_usd"] / uncapped["llm_calls"]
    calls_at_default = (10007 - 4) // 2  # 4 fixed steps, then answer+validate per loop
    print(f"projected at LangGraph's default limit (10007 steps, ~{calls_at_default} calls): "
          f"${per_call * calls_at_default:.2f} for one question")


if __name__ == "__main__":
    main()
