-- Dashboard read access (D42) and drift results in the DB (PLAN M5: eval score with its
-- noise band on the dashboard).

CREATE TABLE IF NOT EXISTS drift_runs (
    id          bigserial   PRIMARY KEY,
    tenant      text        NOT NULL,
    mutation    date,
    phase       text        NOT NULL,   -- baseline | stale | refreshed
    graph       text        NOT NULL,   -- rag | kg
    n_questions int         NOT NULL,
    truth       text        NOT NULL,   -- expected_old | expected
    scores      jsonb       NOT NULL,   -- per run
    mean        real        NOT NULL,
    band_lo     real,
    band_hi     real,
    verdict     text,
    stats       jsonb,                  -- wrong stated, validator rejections, forced abstentions
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Row counts per slice: what the dashboard needs from `chunks`, without chunk text.
CREATE OR REPLACE VIEW chunk_slices AS
SELECT tenant, snapshot_date, chunker, embedder, count(*) AS rows,
       count(*) - count(DISTINCT (doc_id, chunk_index)) AS duplicates, max(created_at) AS ingested_at
FROM chunks GROUP BY 1, 2, 3, 4;

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
    CREATE ROLE grafana_ro LOGIN PASSWORD 'grafana_ro';
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON eval_runs, drift_runs, chunk_slices TO grafana_ro;
-- Explicit grants only: grafana_ro is deliberately NOT in the default privileges, so new
-- tables (and the KG, and chunk text) stay invisible to the dashboard.
