"""`python -m policyground.drift <eval|disagreement|staleness>` — M4 drift measurement (D35).

  eval          run the rag and kg graphs N times on a probe set, scored against the
                old or new truth. --phase baseline stores the noise band (mean +- 2 sigma).
  disagreement  share of properties whose KG value (cancellation window, pet fee)
                differs from what the latest PRODUCTION chunks state.
  staleness     minutes from the KG applying a mutation's facts to the chunks of that
                snapshot being ingested (or "still open").
Every result is appended to METRICS.md, "Drift (M4)".
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from policyground import graph as graph_mod  # noqa: E402
from policyground.config import PRODUCTION  # noqa: E402
from policyground.db import connect  # noqa: E402
from policyground.eval.metrics_md import append_to_table  # noqa: E402
from policyground.eval.score import is_correct  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

SECTION = "## Drift (M4)"
METRICS = Path("METRICS.md")


def record_db(tenant, mutation, phase, graph, n, truth, scores, mean, lo, hi, verdict, stats) -> None:
    """Also store drift results in the DB, for the dashboard (PLAN M5, migration 007)."""
    with connect("ingest_rw") as conn:
        conn.execute("""INSERT INTO drift_runs (tenant, mutation, phase, graph, n_questions, truth, scores,
                        mean, band_lo, band_hi, verdict, stats) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (tenant, mutation, phase, graph, n, truth, Jsonb(scores), mean, lo, hi, verdict, Jsonb(stats)))


def _row(*cells) -> None:
    append_to_table(METRICS, SECTION, "| " + " | ".join(str(c) for c in cells) + " |")


def run_eval(tenant: str, probes: list[dict], expect: str, runs: int) -> tuple[dict, dict]:
    """Returns ({graph: [score per run]}, {graph: validator stats}). The stats separate
    validator rejections and forced abstentions (INCIDENTS #10) from wrong answers."""
    out, stats = {}, {}
    for g in ("rag", "kg"):
        graph = graph_mod.GRAPHS[g]()
        scores, st = [], {"answers": 0, "val_rej": 0, "forced_abstain": 0, "wrong_stated": 0}
        for _ in range(runs):
            ok = 0
            for q in probes:
                s = graph_mod.ask(graph, tenant, q["question"])
                correct = is_correct(q[expect], s["answer"], s["abstain"])
                ok += correct
                st["answers"] += 1
                st["val_rej"] += bool(s.get("validator_problems"))
                st["forced_abstain"] += bool(s.get("forced_abstain"))
                st["wrong_stated"] += (not correct and not s["abstain"])
            scores.append(ok / len(probes))
        out[g], stats[g] = scores, st
    return out, stats


def band(scores: list[float], n_questions: int) -> tuple[float, float]:
    """mean +- 2 sigma, with sigma floored at the eval set's sampling error (D37,
    INCIDENTS #11): sqrt(p(1-p)/n), p clamped to [1/n, 1-1/n] so p = 0 or 1 doesn't
    collapse the floor to zero. A few identical runs then can't produce a zero-width band."""
    m = statistics.mean(scores)
    run_sd = statistics.stdev(scores) if len(scores) > 1 else 0.0
    p = min(max(m, 1 / n_questions), 1 - 1 / n_questions)
    sd = max(run_sd, (p * (1 - p) / n_questions) ** 0.5)
    return m - 2 * sd, m + 2 * sd


def stated(tenant: str) -> dict[str, dict]:
    """Per property, the cancellation window and pet fee the latest production chunks state."""
    with connect("api_ro") as conn:
        rows = conn.execute(
            """SELECT doc_id, string_agg(text, E'\\n' ORDER BY chunk_index) FROM chunks
               WHERE tenant=%s AND chunker=%s AND embedder=%s
                 AND snapshot_date = (SELECT max(snapshot_date) FROM chunks
                                      WHERE tenant=%s AND chunker=%s AND embedder=%s)
               GROUP BY doc_id""",
            (tenant, PRODUCTION["chunker"], PRODUCTION["embedder"],
             tenant, PRODUCTION["chunker"], PRODUCTION["embedder"])).fetchall()
        parents = dict(conn.execute("SELECT id, parent_id FROM entity WHERE tenant=%s", (tenant,)).fetchall())
    text = dict(rows)

    def section(doc: str, title: str) -> str:
        m = re.search(rf"## {title}\n\n(.*?)(?=\n## |\Z)", text.get(doc, ""), re.S)
        return m.group(1) if m else ""

    def window(doc: str, level: str) -> int | None:
        m = re.search(r"(\d+) hours", section(doc, "Cancellation"))
        if m:
            return int(m.group(1))
        parent = parents.get(doc if level == "property" else doc.split("-", 1)[1])
        if level == "property":
            return window(f"brand-{parent}", "brand")
        if level == "brand":
            return window(f"chain-{parent}", "chain")
        return None

    out = {}
    for pid in (d for d in text if d.startswith("P")):
        fee = re.search(r"EUR (\d+)", section(pid, "Pets"))
        out[pid] = {"cancel_window_hours": window(pid, "property"),
                    "pet_fee_eur": int(fee.group(1)) if fee else None}
    return out


def kg_values(tenant: str, pids: list[str]) -> dict[str, dict]:
    with connect("api_ro") as conn:
        out = {}
        for pid in pids:
            pol = {k: v for k, v, *_ in conn.execute("SELECT * FROM resolve_policy(%s, %s)", (tenant, pid))}
            out[pid] = {"cancel_window_hours": pol["cancel_window_hours"],
                        "pet_fee_eur": pol["pet_fee_eur"] if pol["pets_allowed"] else None}
        return out


def disagreement(tenant: str) -> tuple[float, list[str]]:
    s = stated(tenant)
    k = kg_values(tenant, sorted(s))
    bad = [pid for pid in s if s[pid] != k[pid]]
    return len(bad) / len(s), bad


def staleness(tenant: str, date: str) -> str:
    changes = json.loads(Path(f"data/{tenant}/mutations/{date}.json").read_text())
    with connect("api_ro") as conn:
        applied = conn.execute(
            """SELECT max(updated_at) FROM policy_fact WHERE tenant=%s AND (entity_id, key) IN
               (SELECT * FROM unnest(%s::text[], %s::text[]))""",
            (tenant, [c["property_id"] for c in changes], [c["key"] for c in changes])).fetchone()[0]
        ingested = conn.execute(
            """SELECT min(created_at) FROM chunks WHERE tenant=%s AND snapshot_date=%s
               AND chunker=%s AND embedder=%s""",
            (tenant, date, PRODUCTION["chunker"], PRODUCTION["embedder"])).fetchone()[0]
    if ingested is None:
        return f"open: {(datetime.now(timezone.utc) - applied).total_seconds() / 60:.1f} min so far"
    return f"{(ingested - applied).total_seconds() / 60:.1f} min"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["eval", "disagreement", "staleness"])
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date", help="mutation date (probe set / staleness)")
    ap.add_argument("--phase", default="", help="label, e.g. baseline / stale / refreshed")
    ap.add_argument("--expect", choices=["expected_old", "expected"], default="expected")
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    noise_path = Path(f"data/{args.tenant}/drift-noise-{args.date}.json")

    if args.what == "eval":
        probes = json.loads(Path(f"data/{args.tenant}/probes-{args.date}.json").read_text())
        res, stats = run_eval(args.tenant, probes, args.expect, args.runs)
        if args.phase == "baseline":
            noise_path.write_text(json.dumps({g: band(v, len(probes)) for g, v in res.items()}))
        noise = json.loads(noise_path.read_text()) if noise_path.exists() else {}
        for g, scores in res.items():
            lo, hi = noise.get(g, (None, None))
            mean = statistics.mean(scores)
            verdict = ("—" if lo is None or args.phase == "baseline"
                       else "DRIFT (below band)" if mean < lo else "within band" if mean <= hi else "above band")
            band_txt = "—" if lo is None else f"[{lo:.2f}, {hi:.2f}]"
            st = stats[g]
            detail = (f"wrong stated {st['wrong_stated']}/{st['answers']}, val-rej {st['val_rej']}, "
                      f"forced abstain {st['forced_abstain']}")
            verdict = f"{verdict} ({detail})"
            print(f"{args.phase:10s} {g:3s} runs {[round(x, 2) for x in scores]} mean {mean:.2f} "
                  f"band {band_txt} -> {verdict}")
            record_db(args.tenant, args.date, args.phase, g, len(probes), args.expect, scores, mean,
                      lo, hi, verdict, st)
            _row(now, args.date, args.phase, g, len(probes), args.expect,
                 " / ".join(f"{x:.2f}" for x in scores), f"{mean:.2f}", band_txt, verdict, "", "")
    elif args.what == "disagreement":
        rate, bad = disagreement(args.tenant)
        print(f"KG/vector disagreement: {rate:.3f} ({len(bad)} properties) {bad[:10]}")
        _row(now, args.date or "", args.phase, "—", "—", "—", "—", "—", "—", "—", f"{rate:.3f} ({len(bad)})", "")
    else:
        s = staleness(args.tenant, args.date)
        print(f"staleness window for {args.date}: {s}")
        _row(now, args.date, args.phase, "—", "—", "—", "—", "—", "—", "—", "", s)


if __name__ == "__main__":
    main()
