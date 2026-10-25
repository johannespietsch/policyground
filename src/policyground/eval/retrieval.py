"""Retrieval-only evaluation (PLAN M2 comparison, M3 DAG eval task). No LLM calls.

  python -m policyground.eval.retrieval
      every chunker x embedder on its latest snapshot -> METRICS.md comparison table
  python -m policyground.eval.retrieval --date D --chunker C --embedder E --source S
      one slice -> a row in the eval_runs table (what the Airflow DAG runs)

Measured over all answerable golden questions, in two settings:
  unfiltered  similarity search over the whole tenant (the M1 / plain-RAG setting)
  filtered    restricted to the resolved property's lineage docs (what the kg graph sees)
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from psycopg.types.json import Jsonb

from policyground.db import connect
from policyground.eval.metrics_md import append_to_table
from policyground.kg.lookup import property_context
from policyground.retrieve import search
from policyground.tenants.hotels.kg import KG
from policyground.tenants.hotels.render import FEE_TEXT


def surface_text(q: dict, kg: KG) -> str:
    """Text a chunk must contain to actually carry the answer."""
    pol = kg.resolve("property", q["property_id"])
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
    raise ValueError(kind)


def evaluate(tenant: str, chunker: str, embedder: str, snapshot_date: str | None = None,
             root: Path = Path(".")) -> dict:
    kg = KG.load(root / f"data/{tenant}/kg.json")
    golden = [q for q in json.loads((root / f"data/{tenant}/golden.json").read_text())
              if q["expected"]["kind"] != "abstain"]
    manifest = json.loads((root / f"data/{tenant}/manifest-{kg.snapshot_date}.json").read_text())
    lineage = {q["property_id"]: property_context(tenant, q["property_id"])[2] for q in golden}
    # Only where the property doc states the rule itself; a deferring doc can't hold both.
    nr = [q for q in golden if q["expected"]["kind"] == "no_free_cancellation"
          and not manifest[q["property_id"]]["cancel_by_reference"]]

    doc_hit = fact_un = fact_f = together = 0
    for q in golden:
        needle = surface_text(q, kg).lower()
        gov = set(q["governing"]["docs"])
        kw = {"chunker": chunker, "embedder": embedder, "snapshot_date": snapshot_date}
        un = search(tenant, q["question"], **kw)
        fi = search(tenant, q["question"], doc_ids=lineage[q["property_id"]], **kw)
        docs = {c.chunk_id.split("#")[0] for c in un}
        doc_hit += all(d in docs for d in q["evidence_docs"])
        fact_un += any(c.chunk_id.split("#")[0] in gov and needle in c.text.lower() for c in un)
        fact_f += any(c.chunk_id.split("#")[0] in gov and needle in c.text.lower() for c in fi)
        if q in nr:
            window = f"{kg.resolve('property', q['property_id'])['cancel_window_hours']['value']} hours"
            together += any(window in c.text and "non-refundable" in c.text.lower() for c in fi)
    n = len(golden)
    return {"n": n, "doc@5": doc_hit / n, "fact@5_unfiltered": fact_un / n,
            "fact@5_filtered": fact_f / n, "nr_together": together, "nr_n": len(nr)}


def slice_rows(tenant: str, chunker: str, embedder: str, snapshot_date: str) -> int:
    with connect("api_ro") as conn:
        return conn.execute("""SELECT count(*) FROM chunks WHERE tenant=%s AND chunker=%s
                               AND embedder=%s AND snapshot_date=%s""",
                            (tenant, chunker, embedder, snapshot_date)).fetchone()[0]


def record(tenant: str, chunker: str, embedder: str, snapshot_date: str, source: str, m: dict) -> None:
    with connect("ingest_rw") as conn:
        conn.execute(
            """INSERT INTO eval_runs (tenant, snapshot_date, chunker, embedder, source,
                                      n_questions, chunk_rows, metrics)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (tenant, snapshot_date, chunker, embedder, source, m["n"],
             slice_rows(tenant, chunker, embedder, snapshot_date), Jsonb(m)))


def comparison_table(tenant: str = "hotels") -> None:
    with connect("api_ro") as conn:
        combos = conn.execute("SELECT DISTINCT chunker, embedder FROM chunks WHERE tenant = %s ORDER BY 1, 2",
                              (tenant,)).fetchall()
    rows = []
    for chunker, embedder in combos:
        m = evaluate(tenant, chunker, embedder)
        rows.append((chunker, embedder, m))
        print(f"{chunker:14s} {embedder:18s} doc@5 {m['doc@5']:.2f}  fact@5 unfiltered "
              f"{m['fact@5_unfiltered']:.2f}  filtered {m['fact@5_filtered']:.2f}  "
              f"NR rule+exception together {m['nr_together']}/{m['nr_n']}")

    for chunker, embedder, m in rows:
        append_to_table(Path("METRICS.md"), "## Retrieval: hit@5 per chunker × embedder",
                        f"| {date.today()} | {chunker} | {embedder} | {m['n']} | {m['doc@5']:.2f} "
                        f"| {m['fact@5_unfiltered']:.2f} | {m['fact@5_filtered']:.2f} "
                        f"| {m['nr_together']}/{m['nr_n']} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date")
    ap.add_argument("--chunker")
    ap.add_argument("--embedder")
    ap.add_argument("--source", default="manual")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()
    if not args.date:
        comparison_table(args.tenant)
        return
    m = evaluate(args.tenant, args.chunker, args.embedder, args.date, args.root)
    record(args.tenant, args.chunker, args.embedder, args.date, args.source, m)
    print(f"eval {args.date} {args.chunker} x {args.embedder}: {json.dumps(m)} -> eval_runs")


if __name__ == "__main__":
    main()
