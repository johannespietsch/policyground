"""`python -m policyground.ingest.steps <chunk|embed|upsert> --date D` — the M3 DAG's
tasks (D29). Each step reads the previous step's staging file, so Airflow can retry
one step without redoing the others.

  chunk   corpus/<tenant>/<date>/*.md          -> staging/.../chunks.jsonl
  embed   chunks.jsonl                         -> staging/.../embeddings.npy
  upsert  chunks.jsonl + embeddings.npy        -> chunks table (as ingest_rw), idempotent

Embedding is local, so there are no real rate limits. Two ways to simulate a 429 on
the embed step and exercise Airflow's retries (PLAN M3):
  FAIL_RATE=p           each attempt fails with probability p (the plan's knob; random)
  FAIL_FIRST_TRIES=n    attempts 1..n fail, using TRY_NUMBER from Airflow (repeatable)
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

from policyground.config import PRODUCTION
from policyground.tenant import spec as tenant_spec
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
            for i, text in enumerate(CHUNKERS[args.chunker](path.read_text(), tenant_spec(args.tenant))):
                f.write(json.dumps({"doc_id": path.stem, "chunk_index": i, "text": text,
                                    "chunk_hash": hashlib.sha256(text.encode()).hexdigest()}) + "\n")
                n += 1
    print(f"chunk: {n} chunks from {len(docs)} docs -> {out / 'chunks.jsonl'}")


def embed_step(args) -> None:
    fail_rate = float(os.environ.get("FAIL_RATE", "0"))
    fail_first = int(os.environ.get("FAIL_FIRST_TRIES", "0"))
    try_number = int(os.environ.get("TRY_NUMBER", "1"))
    if try_number <= fail_first or random.random() < fail_rate:
        raise SimulatedRateLimit(f"simulated HTTP 429 from embedding provider "
                                 f"(try {try_number}, FAIL_FIRST_TRIES={fail_first}, FAIL_RATE={fail_rate})")
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
        # Idempotent (D30): overwrite the whole slice in ONE transaction, so a retry,
        # a cleared task or a reprocessing backfill leaves exactly one copy, and
        # readers never see a half-written slice. The unique key chunks_slice_key
        # (migration 005) makes a duplicate an error even if this code regresses.
        cur.execute(
            """DELETE FROM chunks WHERE tenant = %s AND snapshot_date = %s
               AND chunker = %s AND embedder = %s""",
            (args.tenant, args.date, args.chunker, args.embedder),
        )
        replaced = cur.rowcount
        cur.executemany(
            """INSERT INTO chunks (tenant, doc_id, snapshot_date, chunker, embedder,
                                   chunk_index, chunk_hash, text, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(args.tenant, r["doc_id"], args.date, args.chunker, args.embedder,
              r["chunk_index"], r["chunk_hash"], r["text"], v) for r, v in zip(rows, vectors)],
        )
    print(f"upsert: replaced {replaced} rows with {len(rows)} chunks for {args.date} "
          f"({args.chunker} x {args.embedder})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["chunk", "embed", "upsert"])
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date", required=True)
    ap.add_argument("--chunker", default=PRODUCTION["chunker"], choices=CHUNKERS)
    ap.add_argument("--embedder", default=PRODUCTION["embedder"], choices=EMBEDDERS)
    ap.add_argument("--root", type=Path, default=Path(os.environ.get("POLICYGROUND_ROOT", ".")))
    args = ap.parse_args()
    {"chunk": chunk, "embed": embed_step, "upsert": upsert}[args.step](args)


if __name__ == "__main__":
    main()
