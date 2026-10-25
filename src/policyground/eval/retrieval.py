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
from policyground import tenant as tenants
from policyground.kg.lookup import subject_context
from policyground.retrieve import search


def subject_of(q: dict) -> str | None:
    """Golden items name their subject as subject_id (any tenant) or property_id (hotels, M1-M5)."""
    return q.get("subject_id", q.get("property_id"))


def needle(q: dict, data: dict, tenant: str) -> str | None:
    """Text a chunk must contain to actually carry the answer: the item's evidence_text,
    else the tenant adapter's evidence_text hook, else None (fact@5 not measured)."""
    if q.get("evidence_text"):
        return q["evidence_text"]
    hook = getattr(tenants.adapter(tenant), "evidence_text", None)
    return hook(q, data) if hook else None


def evaluate(tenant: str, chunker: str, embedder: str, snapshot_date: str | None = None,
             root: Path = Path(".")) -> dict:
    data = json.loads((root / f"data/{tenant}/kg.json").read_text())
    golden = [q for q in json.loads((root / f"data/{tenant}/golden.json").read_text())
              if q["expected"]["kind"] != "abstain" and subject_of(q)]
    lineage = {subject_of(q): subject_context(tenant, subject_of(q))[2] for q in golden}
    # Rule + exception in one chunk: only for golden items that declare both texts.
    together_qs = [q for q in golden if q.get("rule_text") and q.get("exception_text")]
    hook = getattr(tenants.adapter(tenant), "rule_and_exception", None)
    if hook and not together_qs:
        together_qs = [q for q in golden if hook(q, data, root)]

    doc_hit = fact_un = fact_f = together = measured = 0
    for q in golden:
        text = needle(q, data, tenant)
        gov = set(q["governing"]["docs"])
        kw = {"chunker": chunker, "embedder": embedder, "snapshot_date": snapshot_date}
        un = search(tenant, q["question"], **kw)
        fi = search(tenant, q["question"], doc_ids=lineage[subject_of(q)], **kw)
        docs = {c.chunk_id.split("#")[0] for c in un}
        doc_hit += all(d in docs for d in q["evidence_docs"])
        if text:
            measured += 1
            fact_un += any(c.chunk_id.split("#")[0] in gov and text.lower() in c.text.lower() for c in un)
            fact_f += any(c.chunk_id.split("#")[0] in gov and text.lower() in c.text.lower() for c in fi)
        if q in together_qs:
            rule, exc = (q.get("rule_text"), q.get("exception_text")) if q.get("rule_text") else hook(q, data, root)
            together += any(rule.lower() in c.text.lower() and exc.lower() in c.text.lower() for c in fi)
    n = len(golden)
    return {"n": n, "doc@5": doc_hit / n,
            "fact@5_unfiltered": fact_un / measured if measured else None,
            "fact@5_filtered": fact_f / measured if measured else None,
            "nr_together": together, "nr_n": len(together_qs)}


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


def _f(x) -> str:
    return "—" if x is None else f"{x:.2f}"


def comparison_table(tenant: str = "hotels") -> None:
    with connect("api_ro") as conn:
        combos = conn.execute("SELECT DISTINCT chunker, embedder FROM chunks WHERE tenant = %s ORDER BY 1, 2",
                              (tenant,)).fetchall()
    rows = []
    for chunker, embedder in combos:
        m = evaluate(tenant, chunker, embedder)
        rows.append((chunker, embedder, m))
        print(f"{chunker:14s} {embedder:18s} doc@5 {m['doc@5']:.2f}  fact@5 unfiltered "
              f"{_f(m['fact@5_unfiltered'])}  filtered {_f(m['fact@5_filtered'])}  "
              f"rule+exception together {m['nr_together']}/{m['nr_n']}")

    for chunker, embedder, m in rows:
        append_to_table(Path("METRICS.md"), "## Retrieval: hit@5 per chunker × embedder",
                        f"| {date.today()} | {chunker} | {embedder} | {m['n']} | {m['doc@5']:.2f} "
                        f"| {_f(m['fact@5_unfiltered'])} | {_f(m['fact@5_filtered'])} "
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
