-- Retrieval index. One table for every chunker x embedder combination (D16).
CREATE TABLE IF NOT EXISTS chunks (
    id            bigserial PRIMARY KEY,
    tenant        text        NOT NULL,
    doc_id        text        NOT NULL,   -- corpus file stem: P001, brand-C1-B1, chain-C1
    snapshot_date date        NOT NULL,
    chunker       text        NOT NULL,   -- e.g. naive-800
    embedder      text        NOT NULL,   -- e.g. bge-small-en-v1.5
    chunk_index   int         NOT NULL,
    chunk_hash    text        NOT NULL,   -- sha256 of text
    text          text        NOT NULL,
    -- Untyped so embedders of different dimensions share the table. That rules
    -- out an HNSW index; retrieval is an exact scan, filtered by embedder (D16).
    embedding     vector      NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
    -- Deliberately NO unique key on (tenant, doc_id, snapshot_date, chunker,
    -- embedder, chunk_hash) yet: M1 ingest truncates and reloads; M3 backfill
    -- will hit the duplicate-chunk bug and fix it as an incident (D17).
);

CREATE INDEX IF NOT EXISTS chunks_lookup
    ON chunks (tenant, chunker, embedder, snapshot_date);
