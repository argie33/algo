-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION 052: Create algo_signals table with entry_stage column
-- ════════════════════════════════════════════════════════════════════════════
-- Issue: #4 Missing Database Columns
-- Purpose: Create the base algo_signals table that tracks market entry stages
--
-- The algo_signals table stores signal evaluation results before trade execution,
-- including the chart stage at signal entry (entry_stage) which is used for
-- portfolio analysis and distribution reporting.

CREATE TABLE IF NOT EXISTS algo_signals (
    id SERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    source_table VARCHAR(50),
    source_timeframe VARCHAR(20),
    raw_signal VARCHAR(20),
    entry_price DECIMAL(12, 4),
    entry_stage VARCHAR(20),
    signal_active BOOLEAN DEFAULT TRUE,
    signal_quality_score INTEGER,
    risk_score DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_date, symbol, source_timeframe)
);

CREATE INDEX IF NOT EXISTS idx_algo_signals_symbol_date ON algo_signals(symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_algo_signals_entry_stage ON algo_signals(entry_stage) WHERE entry_stage IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_algo_signals_active ON algo_signals(signal_active);
