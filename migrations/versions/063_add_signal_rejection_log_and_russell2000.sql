-- Migration 063: Add signal_rejection_log table and is_russell2000 column
-- signal_rejection_log: tracks which symbols were rejected by loaders and why
--   Used by load_buy_sell_daily.py and load_swing_trader_scores.py for observability.
--   Table referenced in code but never created as a versioned migration.
-- is_russell2000: flag on stock_symbols for Russell 2000 constituent tracking
--   Used by load_russell2000_constituents.py loader.

CREATE TABLE IF NOT EXISTS signal_rejection_log (
    id SERIAL PRIMARY KEY,
    signal_source_table VARCHAR(100) NOT NULL,
    rejection_reason TEXT,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE,
    rejected_at_tier VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_signal_rejection_symbol ON signal_rejection_log(symbol);
CREATE INDEX IF NOT EXISTS idx_signal_rejection_date ON signal_rejection_log(signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_rejection_source ON signal_rejection_log(signal_source_table);

ALTER TABLE stock_symbols ADD COLUMN IF NOT EXISTS is_russell2000 BOOLEAN DEFAULT FALSE;
