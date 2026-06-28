#!/usr/bin/env python3
"""
Migration 003: Remove algo_runtime_config and algo_runtime_config_audit tables.

The RuntimeConfig system was designed as a separate hot-reload layer for 6 "operational toggle"
keys, but proved redundant and is dead code (RuntimeConfig.get() is called zero times in
production). The unified algo_config table + per-invocation singleton reset in Lambda is the
correct pattern. This migration removes the orphaned tables.

Reversible: down() recreates both tables with original seed data.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Remove unused algo_runtime_config and algo_runtime_config_audit tables"


def up():
    """Drop the runtime config tables."""
    with DatabaseContext("write") as cur:
        # Audit table first (has FK dependency)
        cur.execute("DROP TABLE IF EXISTS algo_runtime_config_audit CASCADE")
        # Main config table
        cur.execute("DROP TABLE IF EXISTS algo_runtime_config CASCADE")


def down():
    """Recreate the runtime config tables with original schema and seed data."""
    with DatabaseContext("write") as cur:
        # Recreate main config table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS algo_runtime_config (
                config_key VARCHAR(100) PRIMARY KEY,
                config_value VARCHAR(1000) NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by VARCHAR(100) DEFAULT 'system',
                CONSTRAINT valid_config_key CHECK (config_key ~ '^[a-z_]+$')
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_runtime_config_updated_at
            ON algo_runtime_config(updated_at DESC)
        """)

        # Seed initial data
        cur.execute("""
            INSERT INTO algo_runtime_config (config_key, config_value, description, updated_by) VALUES
                ('alpaca_trading_mode', 'paper', 'Trading mode: paper | live | disabled', 'system'),
                ('max_position_size_usd', '5000', 'Maximum position size in USD per symbol', 'system'),
                ('circuit_breaker_vix_threshold', '50', 'VIX level to halt trading', 'system'),
                ('data_freshness_sla_hours', '24', 'Maximum hours before Phase 1 data freshness halt', 'system'),
                ('orchestrator_enabled', 'true', 'Enable/disable orchestrator execution', 'system'),
                ('execution_monitor_enabled', 'true', 'Enable/disable execution monitor checks', 'system')
            ON CONFLICT (config_key) DO NOTHING
        """)

        # Recreate audit table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS algo_runtime_config_audit (
                id SERIAL PRIMARY KEY,
                config_key VARCHAR(100) NOT NULL,
                old_value VARCHAR(1000),
                new_value VARCHAR(1000) NOT NULL,
                changed_by VARCHAR(100) DEFAULT 'system',
                change_reason TEXT DEFAULT '',
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (config_key) REFERENCES algo_runtime_config(config_key) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_config_audit_changed_at
            ON algo_runtime_config_audit(changed_at DESC)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_config_audit_key
            ON algo_runtime_config_audit(config_key)
        """)

        # Grant permissions
        cur.execute("GRANT SELECT ON algo_runtime_config TO stocks")
        cur.execute("GRANT SELECT ON algo_runtime_config_audit TO stocks")
