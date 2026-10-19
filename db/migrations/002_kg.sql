-- Knowledge graph as an adjacency list (D21). The hierarchy is
-- chain -> brand -> property -> rate_plan, but nothing here hard-codes the depth.
CREATE TABLE IF NOT EXISTS entity (
    tenant     text  NOT NULL,
    id         text  NOT NULL,
    type       text  NOT NULL CHECK (type IN ('chain', 'brand', 'property', 'rate_plan')),
    parent_id  text,
    name       text,
    attrs      jsonb NOT NULL DEFAULT '{}',   -- type-specific: city, rate-plan kind
    PRIMARY KEY (tenant, id),
    FOREIGN KEY (tenant, parent_id) REFERENCES entity (tenant, id),
    CHECK ((type = 'chain') = (parent_id IS NULL))
);

-- One current value per (entity, key). valid_from lets M4's event consumer
-- refuse to overwrite a newer value with an older, re-delivered one.
CREATE TABLE IF NOT EXISTS policy_fact (
    tenant     text  NOT NULL,
    entity_id  text  NOT NULL,
    key        text  NOT NULL,
    value      jsonb NOT NULL,
    valid_from date  NOT NULL,
    PRIMARY KEY (tenant, entity_id, key),
    FOREIGN KEY (tenant, entity_id) REFERENCES entity (tenant, id)
);

-- Effective policy for one entity: walk up to the root, most specific level wins.
-- Must agree with policyground.seed.kg.KG.resolve (tested).
CREATE OR REPLACE FUNCTION resolve_policy(p_tenant text, p_entity_id text)
RETURNS TABLE (key text, value jsonb, source_id text, source_type text, depth int)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE lineage AS (
        SELECT e.id, e.type, e.parent_id, 0 AS depth
        FROM entity e
        WHERE e.tenant = p_tenant AND e.id = p_entity_id
      UNION ALL
        SELECT e.id, e.type, e.parent_id, l.depth + 1
        FROM entity e
        JOIN lineage l ON e.tenant = p_tenant AND e.id = l.parent_id
        WHERE l.depth < 10          -- guard against a cycle in bad data
    )
    SELECT DISTINCT ON (f.key) f.key, f.value, l.id, l.type, l.depth
    FROM lineage l
    JOIN policy_fact f ON f.tenant = p_tenant AND f.entity_id = l.id
    ORDER BY f.key, l.depth          -- depth 0 = the entity itself = most specific
$$;
