"""`python -m policyground.eval.retrieval` — retrieval-only comparison of every
chunker x embedder in `chunks` (PLAN M2). No LLM calls.

Measured over all answerable golden questions, in two settings:
  unfiltered  similarity search over the whole tenant (the M1 / plain-RAG setting)
  filtered    restricted to the resolved property's lineage docs (what the kg graph sees)
"""

from __future__ import annotations

import json
from pathlib import Path

from policyground.db import connect
from policyground.kg.lookup import property_context
from policyground.retrieve import search
from policyground.seed.kg import KG
from policyground.seed.render import FEE_TEXT


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


def main() -> None:
    tenant = "hotels"
    kg = KG.load(Path(f"data/{tenant}/kg.json"))
    golden = [q for q in json.loads(Path(f"data/{tenant}/golden.json").read_text())
              if q["expected"]["kind"] != "abstain"]
    with connect("api_ro") as conn:
        combos = conn.execute("SELECT DISTINCT chunker, embedder FROM chunks WHERE tenant = %s ORDER BY 1, 2",
                              (tenant,)).fetchall()
    lineage = {q["property_id"]: property_context(tenant, q["property_id"])[2] for q in golden}
    nr = [q for q in golden if q["expected"]["kind"] == "no_free_cancellation"]

    rows = []
    for chunker, embedder in combos:
        doc_hit = fact_un = fact_f = together = 0
        for q in golden:
            needle = surface_text(q, kg).lower()
            gov = set(q["governing"]["docs"])
            un = search(tenant, q["question"], chunker=chunker, embedder=embedder)
            fi = search(tenant, q["question"], chunker=chunker, embedder=embedder, doc_ids=lineage[q["property_id"]])
            docs = {c.chunk_id.split("#")[0] for c in un}
            doc_hit += all(d in docs for d in q["evidence_docs"])
            fact_un += any(c.chunk_id.split("#")[0] in gov and needle in c.text.lower() for c in un)
            fact_f += any(c.chunk_id.split("#")[0] in gov and needle in c.text.lower() for c in fi)
            if q in nr:
                window = f"{kg.resolve('property', q['property_id'])['cancel_window_hours']['value']} hours"
                together += any(window in c.text and "non-refundable" in c.text.lower() for c in fi)
        n = len(golden)
        rows.append((chunker, embedder, n, doc_hit / n, fact_un / n, fact_f / n, f"{together}/{len(nr)}"))
        print(f"{chunker:14s} {embedder:18s} doc@5 {doc_hit / n:.2f}  fact@5 unfiltered {fact_un / n:.2f}  "
              f"filtered {fact_f / n:.2f}  NR rule+exception together {together}/{len(nr)}")

    metrics = Path("METRICS.md")
    text = metrics.read_text()
    header = "## Retrieval: hit@5 per chunker × embedder"
    if header not in text:
        text += f"""
{header}

Written by `python -m policyground.eval.retrieval`. Retrieval only, no LLM. Over all
answerable golden questions (headline, fuzzy and hard), top-5.

| Column | Definition |
|---|---|
| doc@5 | Every evidence doc has a chunk in the top 5 (unfiltered). Same definition as hit@5 in the eval table. Blind to chunk boundaries. |
| fact@5 unf. | A top-5 chunk from the governing doc **contains the fact text** (e.g. "48 hours", "non-refundable", "EUR 25"). Unfiltered: the plain-RAG setting. |
| fact@5 filt. | Same, with search restricted to the resolved property's lineage docs: what the kg graph sees. |
| NR together | Non-refundable questions where one retrieved (filtered) chunk holds **both** the cancellation rule and the exception, i.e. the chunk boundary didn't separate them. |

| date | chunker | embedder | n | doc@5 | fact@5 unf. | fact@5 filt. | NR together |
|---|---|---|---|---|---|---|---|
"""
    from datetime import date
    for chunker, embedder, n, d, fu, ff, t in rows:
        text += f"| {date.today()} | {chunker} | {embedder} | {n} | {d:.2f} | {fu:.2f} | {ff:.2f} | {t} |\n"
    metrics.write_text(text)


if __name__ == "__main__":
    main()
