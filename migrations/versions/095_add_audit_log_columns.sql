-- Migration: Add audit log columns for operation tracking
-- Issue: audit_logger.py expects operation_type, entity_type, entity_id, operation_details
-- but schema.sql only had action_type, symbol, details
-- This adds the expected columns to enable portfolio snapshot and position reconciliation auditing

ALTER TABLE algo_audit_log ADD COLUMN IF NOT EXISTS operation_type VARCHAR(50);
ALTER TABLE algo_audit_log ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50);
ALTER TABLE algo_audit_log ADD COLUMN IF NOT EXISTS entity_id VARCHAR(100);
ALTER TABLE algo_audit_log ADD COLUMN IF NOT EXISTS operation_details TEXT;

-- Create index for operation_type queries
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_operation_type ON algo_audit_log(operation_type);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_entity_type ON algo_audit_log(entity_type);
