-- Idempotency (D30, INCIDENTS #7). Remove the duplicates the M3 re-run backfill
-- created (keeping the earliest copy), then make duplicates impossible.
DELETE FROM chunks c
USING chunks keep
WHERE c.tenant = keep.tenant AND c.doc_id = keep.doc_id
  AND c.snapshot_date = keep.snapshot_date AND c.chunker = keep.chunker
  AND c.embedder = keep.embedder AND c.chunk_index = keep.chunk_index
  AND c.id > keep.id;

CREATE UNIQUE INDEX IF NOT EXISTS chunks_slice_key
    ON chunks (tenant, doc_id, snapshot_date, chunker, embedder, chunk_index);
