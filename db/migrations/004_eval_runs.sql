-- Results of the DAG's eval task (PLAN M3): retrieval-only metrics per snapshot (D29).
CREATE TABLE IF NOT EXISTS eval_runs (
    id            bigserial   PRIMARY KEY,
    tenant        text        NOT NULL,
    snapshot_date date        NOT NULL,
    chunker       text        NOT NULL,
    embedder      text        NOT NULL,
    source        text        NOT NULL,   -- e.g. airflow:ingest_policies:<run_id>, or manual
    n_questions   int         NOT NULL,
    chunk_rows    int         NOT NULL,   -- rows in this slice at eval time (duplicates show here)
    metrics       jsonb       NOT NULL,   -- doc@5, fact@5 unfiltered / filtered, NR together
    created_at    timestamptz NOT NULL DEFAULT now()
);
