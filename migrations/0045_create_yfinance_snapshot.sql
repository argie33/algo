-- Migration 0045: Create yfinance_snapshot table
-- Consolidates all yfinance data (PE, PB, PS, dividend, beta, holdings, etc.)
-- into single table to eliminate redundant API calls from value_metrics, positioning_metrics, stability_metrics

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

    -- Indexes for fast lookups
    CONSTRAINT yfinance_snapshot_symbol_fk FOREIGN KEY (symbol) REFERENCES stock_symbols(symbol) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_yfinance_snapshot_fetched_at ON yfinance_snapshot(fetched_at);
CREATE INDEX IF NOT EXISTS idx_yfinance_snapshot_data_available ON yfinance_snapshot(data_available);

-- Grant permissions to loaders
GRANT SELECT, INSERT, UPDATE ON yfinance_snapshot TO app_loader;
