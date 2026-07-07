-- Migration 1006: Create yfinance_snapshot table
-- Consolidates all yfinance data (PE, PB, PS, dividend, beta, holdings, etc.)
-- into single table to eliminate redundant API calls from value_metrics, positioning_metrics, stability_metrics
--
-- Moved from migrations/0045_create_yfinance_snapshot.sql (root-level migrations/ is never applied --
-- only migrations/versions/ gets copied into the db-init Lambda package by deploy-all-infrastructure.yml).
-- This table's absence caused loaders/load_value_metrics.py to fail on every symbol with
-- 'relation "yfinance_snapshot" does not exist', driving value_metrics coverage down to ~15% and
-- blocking stock_scores' pre-flight validation (requires 30%+ coverage), which in turn left
-- growth_score (and the rest of stock_scores) stuck stale in the dashboard.
--
-- Dropped the original's "GRANT ... TO app_loader" -- that role does not exist in this deployment
-- (single app DB user owns everything it creates); the grant would have aborted this migration.

CREATE TABLE IF NOT EXISTS yfinance_snapshot (
    symbol VARCHAR(10) PRIMARY KEY,
    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Value metrics (from value_metrics)
    pe_ratio DECIMAL(10, 2),
    pb_ratio DECIMAL(10, 2),
    ps_ratio DECIMAL(10, 2),
    peg_ratio DECIMAL(10, 2),
    dividend_yield DECIMAL(8, 6),
    fcf_yield DECIMAL(8, 6),

    -- Positioning metrics (from positioning_metrics)
    held_percent_insiders DECIMAL(5, 2),
    held_percent_institutions DECIMAL(5, 2),
    short_interest DECIMAL(5, 2),

    -- Stability metrics (from stability_metrics)
    beta DECIMAL(8, 4),
    fifty_two_week_high DECIMAL(12, 2),
    fifty_two_week_low DECIMAL(12, 2),
    market_cap BIGINT,

    -- Data quality flags
    data_available BOOLEAN DEFAULT TRUE,
    unavailable_reason VARCHAR(255),

    CONSTRAINT yfinance_snapshot_symbol_fk FOREIGN KEY (symbol) REFERENCES stock_symbols(symbol) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_yfinance_snapshot_fetched_at ON yfinance_snapshot(fetched_at);
CREATE INDEX IF NOT EXISTS idx_yfinance_snapshot_data_available ON yfinance_snapshot(data_available);
