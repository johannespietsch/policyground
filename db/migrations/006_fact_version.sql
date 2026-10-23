-- Out-of-order guard (D34) and staleness measurement (D35).
-- version: partner-assigned, monotonically increasing per (entity, key). A write only
--          applies if its version is greater than the stored one.
-- updated_at: when the KG last applied a change to this fact (staleness window start).
ALTER TABLE policy_fact ADD COLUMN IF NOT EXISTS version    bigint      NOT NULL DEFAULT 1;
ALTER TABLE policy_fact ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
