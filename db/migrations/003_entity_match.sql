-- Fuzzy entity resolution for the route node (D22).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS entity_name_trgm
    ON entity USING gin (name gin_trgm_ops) WHERE type = 'property';
