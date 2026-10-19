"""Vector retrieval over `chunks`, as api_ro (D15). Exact scan, filtered by embedder (D16)."""

from __future__ import annotations

from dataclasses import dataclass

from policyground.db import connect
from policyground.ingest.embed import embed


@dataclass
class Chunk:
    chunk_id: str  # "<doc_id>#<chunk_index>": stable across reloads, unlike the row id
    text: str
    distance: float


def search(tenant: str, question: str, k: int = 5,
           chunker: str = "naive-800", embedder: str = "bge-small-en-v1.5",
           doc_ids: list[str] | None = None) -> list[Chunk]:
    """doc_ids restricts the search to those documents (the KG route passes the
    resolved property's lineage: property, brand and chain docs)."""
    [qvec] = embed(embedder, [question])
    with connect("api_ro") as conn:
        rows = conn.execute(
            """SELECT doc_id || '#' || chunk_index, text, embedding <=> %s AS distance
               FROM chunks
               WHERE tenant = %s AND chunker = %s AND embedder = %s
                 AND (%s::text[] IS NULL OR doc_id = ANY(%s::text[]))
                 AND snapshot_date = (SELECT max(snapshot_date) FROM chunks
                                      WHERE tenant = %s AND chunker = %s AND embedder = %s)
               ORDER BY distance LIMIT %s""",
            (qvec, tenant, chunker, embedder, doc_ids, doc_ids, tenant, chunker, embedder, k),
        ).fetchall()
    return [Chunk(*r) for r in rows]
