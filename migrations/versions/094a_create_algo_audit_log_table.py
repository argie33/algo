#!/usr/bin/env python3
"""
Migration 094a: Create algo_audit_log table

This table was referenced in migration 095 and throughout the codebase
but the CREATE TABLE statement was never executed. This migration creates
the table with all required columns for audit logging, circuit breaker
tracking, and trade execution history.

CRITICAL FIX: This must run BEFORE migration 095 which tries to add columns
to this table. Without this table, the orchestrator, circuit breaker, and
audit endpoints all fail with UndefinedTable errors.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Create algo_audit_log table for trading activity audit trail"


def up():
    with DatabaseContext("write") as cur:
        # First drop the table if it exists to ensure clean schema
        # (If prior migration failed partway, table might exist in incomplete state)
        cur.execute("DROP TABLE IF EXISTS algo_audit_log CASCADE;")

        # Create main audit log table
        # Tracks all trading actions, circuit breaker state changes, position reconciliation, etc.
        cur.execute("""
            CREATE TABLE algo_audit_log (
                id SERIAL PRIMARY KEY,
                action_type VARCHAR(100) NOT NULL,
                symbol VARCHAR(20),
                action_date TIMESTAMP WITH TIME ZONE,
                details JSONB,
                actor VARCHAR(100),
                status VARCHAR(50),
                error_message TEXT,
                severity VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                -- Columns for extended audit trail (migration 095 expects these)
                operation_type VARCHAR(50),
                entity_type VARCHAR(50),
                entity_id VARCHAR(100),
                operation_details TEXT,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create indexes for common query patterns
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_audit_log_created_at
            ON algo_audit_log(created_at DESC);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_audit_log_action_type
            ON algo_audit_log(action_type);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_audit_log_symbol
            ON algo_audit_log(symbol);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_audit_log_actor
            ON algo_audit_log(actor);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_audit_log_operation_type
            ON algo_audit_log(operation_type);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_algo_audit_log_entity_type
            ON algo_audit_log(entity_type);
        """)

    return True


def down():
    """Drop algo_audit_log table."""
    with DatabaseContext("write") as cur:
        cur.execute("DROP TABLE IF EXISTS algo_audit_log CASCADE;")
    return True
