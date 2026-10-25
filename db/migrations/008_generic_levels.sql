-- Tenant-specific hierarchy levels (D44): the hotel level names were a CHECK constraint.
-- Level names and the parent/child order now come from tenants/<t>/spec.yaml and are
-- validated by the KG loader (policyground.kg) before anything is written.
ALTER TABLE entity DROP CONSTRAINT IF EXISTS entity_type_check;
ALTER TABLE entity DROP CONSTRAINT IF EXISTS entity_check;
