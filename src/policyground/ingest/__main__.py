"""`python -m policyground.ingest` — chunk, embed and load one corpus snapshot.

M1 semantics: delete this (tenant, snapshot, chunker, embedder) slice, then
insert. Proper keyed upserts come in M3 (D17).
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from policyground.db import connect
from policyground.ingest.chunkers import CHUNKERS
from policyground.ingest.embed import EMBEDDERS, embed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hotels")
    ap.add_argument("--date", default="2026-10-16")
    ap.add_argument("--chunker", default="naive-800", choices=CHUNKERS)
    ap.add_argument("--embedder", default="bge-small-en-v1.5", choices=EMBEDDERS)
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()

    corpus_dir = args.root / "corpus" / args.tenant / args.date
    docs = sorted(corpus_dir.glob("*.md"))
    if not docs:
        raise SystemExit(f"no docs in {corpus_dir}; run `make seed` first")

    rows = []
    for path in docs:
        for i, text in enumerate(CHUNKERS[args.chunker](path.read_text())):
            rows.append((path.stem, i, hashlib.sha256(text.encode()).hexdigest(), text))
    vectors = embed(args.embedder, [r[3] for r in rows])

    slice_ = (args.tenant, args.date, args.chunker, args.embedder)
    with connect("ingest_rw") as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM chunks WHERE tenant=%s AND snapshot_date=%s AND chunker=%s AND embedder=%s",
            slice_,
        )
        cur.executemany(
            """INSERT INTO chunks (tenant, doc_id, snapshot_date, chunker, embedder,
                                   chunk_index, chunk_hash, text, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(args.tenant, doc_id, args.date, args.chunker, args.embedder, i, h, text, vec)
             for (doc_id, i, h, text), vec in zip(rows, vectors)],
        )
    print(f"loaded {len(rows)} chunks from {len(docs)} docs ({args.chunker} x {args.embedder})")


if __name__ == "__main__":
    main()
