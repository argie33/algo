-- Migration 095: Verify audit log columns exist (created in migration 094a)
-- This migration is now a verification-only migration since migration 094a
-- creates the complete table with all columns.
--
-- The columns operation_type, entity_type, entity_id, operation_details are
-- now created directly in the CREATE TABLE statement in 094a to avoid
-- ALTER TABLE failures on a non-existent table.
--
-- This migration serves as documentation and verification.

-- Verify the table exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'algo_audit_log'
    ) THEN
        RAISE EXCEPTION 'algo_audit_log table not found - migration 094a should have created it';
    END IF;
END $$;

-- Verify indexes exist (created in 094a, but redundant creation is safe)
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_operation_type ON algo_audit_log(operation_type);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_entity_type ON algo_audit_log(entity_type);
