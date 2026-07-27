-- Migration 1160: Create algo_config_audit table
--
-- CRITICAL: algo_config_audit has been written to by algo/infrastructure/config/main.py's
-- AlgoConfig.update_config() (the governed config-change path used by every admin config
-- edit) and by migrations 033 and 1143 for as long as those exist - but no CREATE TABLE for
-- it exists anywhere in migrations/ or lambda/db-init/schema.sql. The table exists in the
-- live database (verified via information_schema.columns), meaning it was created out-of-
-- band and never captured in tracked schema. A fresh database provisioned purely from
-- schema.sql + migrations - local dev, disaster recovery, a new CI test DB - would be
-- missing this table entirely, and every one of those INSERT INTO algo_config_audit calls
-- would fail with "relation does not exist". This migration codifies the table's actual
-- live schema (columns/types/indexes verified directly against the database) so schema
-- provisioning is no longer silently dependent on undocumented manual DDL.
--
-- This is itself an audit-trail table for risk-critical config changes (halt_drawdown_pct,
-- max_daily_loss_pct, sector_drawdown_halt_pct, etc.) - for a system that must be
-- accurate and auditable, having its own audit table be undocumented schema drift is
-- exactly the kind of gap "bulletproof" is supposed to rule out.

CREATE TABLE IF NOT EXISTS algo_config_audit (
    audit_id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(100),
    change_reason TEXT,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_algo_config_audit_key ON algo_config_audit(config_key);
CREATE INDEX IF NOT EXISTS idx_algo_config_audit_date ON algo_config_audit(changed_at);
