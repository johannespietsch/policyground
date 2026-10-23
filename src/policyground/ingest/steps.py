"""`python -m policyground.ingest.steps <chunk|embed|upsert> --date D` — the M3 DAG's
tasks (D29). Each step reads the previous step's staging file, so Airflow can retry
one step without redoing the others.

  chunk   corpus/<tenant>/<date>/*.md          -> staging/.../chunks.jsonl
  embed   chunks.jsonl                         -> staging/.../embeddings.npy
  upsert  chunks.jsonl + embeddings.npy        -> chunks table (as ingest_rw)

Embedding is local, so there are no real rate limits. FAIL_RATE (0..1) simulates a
429 on the embed step to exercise Airflow's retries (PLAN M3).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path

import numpy as np

from policyground.db import connect
from policyground.ingest.chunkers import CHUNKERS
from policyground.ingest.embed import EMBEDDERS, embed


class SimulatedRateLimit(Exception):
    """Stand-in for an embedding API's HTTP 429."""


def staging_dir(root: Path, tenant: str, date: str, chunker: str, embedder: str) -> Path:
    return root / "data" / tenant / "staging" / date / f"{chunker}__{embedder}"


def chunk(args) -> None:
    corpus = args.root / "corpus" / args.tenant / args.date
    docs = sorted(corpus.glob("*.md"))
    if not docs:
        sys.exit(f"no docs in {corpus}")
    out = staging_dir(args.root, args.tenant, args.date, args.chunker, args.embedder)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out / "chunks.jsonl", "w") as f:
        for path in docs:
            for i, text in enumerate(CHUNKERS[args.chunker](path.read_text())):
                f.write(json.dumps({"doc_id": path.stem, "chunk_index": i, "text": text,
                                    "chunk_hash": hashlib.sha256(text.encode()).hexdigest()}) + "\n")
                n += 1
    print(f"chunk: {n} chunks from {len(docs)} docs -> {out / 'chunks.jsonl'}")


def embed_step(args) -> None:
    fail_rate = float(os.environ.get("FAIL_RATE", "0"))
    if random.random() < fail_rate:
        raise SimulatedRateLimit(f"simulated HTTP 429 from embedding provider (FAIL_RATE={fail_rate})")
    out = staging_dir(args.root, args.tenant, args.date, args.chunker, args.embedder)
    rows = [json.loads(line) for line in open(out / "chunks.jsonl")]
    vectors = np.stack(embed(args.embedder, [r["text"] for r in rows]))
    np.save(out / "embeddings.npy", vectors)
    print(f"embed: {vectors.shape[0]} x {vectors.shape[1]} -> {out / 'embeddings.npy'}")


def upsert(args) -> None:
    out = staging_dir(args.root, args.tenant, args.date, args.chunker, args.embedder)
    rows = [json.loads(line) for line in open(out / "chunks.jsonl")]
    vectors = np.load(out / "embeddings.npy")
    assert len(rows) == len(vectors), "chunks and embeddings out of step"
    with connect("ingest_rw") as conn, conn.cursor() as cur:
        # DELIBERATELY NAIVE (D17): plain INSERT, no key, no delete. Re-running a
        # DAG run (a retry after a partial failure, or a backfill with
        # --reprocess-behavior completed) duplicates every chunk. M3 measures what
        # that does, then fixes it (INCIDENTS).
        cur.executemany(
            """INSERT INTO chunks (tenant, doc_id, snapshot_date, chunker, embedder,
                                   chunk_index, chunk_hash, text, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(args.tenant, r["doc_id"], args.date, args.chunker, args.embedder,
              r["chunk_index"], r["chunk_hash"], r["text"], v) for r, v in zip(rows, vectors)],
        )
    print(f"upsert: inserted {len(rows)} chunks for {args.date} ({args.chunker} x {args.embedder})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["chunk", "embed", "upsert"])
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date", required=True)
    ap.add_argument("--chunker", default="naive-800", choices=CHUNKERS)
    ap.add_argument("--embedder", default="bge-small-en-v1.5", choices=EMBEDDERS)
    ap.add_argument("--root", type=Path, default=Path(os.environ.get("POLICYGROUND_ROOT", ".")))
    args = ap.parse_args()
    {"chunk": chunk, "embed": embed_step, "upsert": upsert}[args.step](args)


if __name__ == "__main__":
    main()
