-- Migration 1012: Create short_interest_finra table for FINRA regulatory short interest data
-- Purpose: Replace yfinance short_interest with official FINRA Reg SHO Transparency Data
-- Date: 2026-07-18
-- Effort: Phase 1 of data source optimization (reduces yfinance dependency by 20%)

-- Table: short_interest_finra
-- Official short interest data from FINRA (the regulatory body that publishes this data).
-- yfinance is a reseller of FINRA data; we fetch the source directly.
-- Updated bi-weekly (not daily, but sufficient for stock scoring)
-- One row per symbol per settlement date (typically Tuesday & Thursday)
CREATE TABLE IF NOT EXISTS short_interest_finra (
    symbol VARCHAR(20) NOT NULL,
    settlement_date DATE NOT NULL,

    short_shares BIGINT,                    -- Total shares short (from FINRA)
    short_pct DECIMAL(6, 2),                -- Short % = (short_shares / float_shares) * 100 (can be computed later)

    finra_report_date DATE,                 -- Date FINRA published this data

    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (symbol, settlement_date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_short_interest_finra_settlement_date
    ON short_interest_finra(settlement_date DESC);
CREATE INDEX IF NOT EXISTS idx_short_interest_finra_unavailable
    ON short_interest_finra(data_unavailable);
CREATE INDEX IF NOT EXISTS idx_short_interest_finra_symbol
    ON short_interest_finra(symbol);

-- Comment
COMMENT ON TABLE short_interest_finra IS 'Official bi-weekly short interest data from FINRA Reg SHO Transparency Data. Replaces yfinance short_interest. FINRA is the authoritative source (yfinance is a reseller).';
COMMENT ON COLUMN short_interest_finra.short_shares IS 'Total shares short in settlement cycle (from FINRA SHO Volume in trades)';
COMMENT ON COLUMN short_interest_finra.short_pct IS 'Short interest as % of float (can be computed from short_shares / outstanding_shares)';
COMMENT ON COLUMN short_interest_finra.settlement_date IS 'Settlement date of the short position (Tuesday or Thursday for 2-day cycles)';
COMMENT ON COLUMN short_interest_finra.finra_report_date IS 'Date FINRA published this report (bi-weekly)';

-- Initial loader status for data_loader_status tracking
INSERT INTO data_loader_status (table_name, status, last_updated, execution_started, execution_completed, error_message)
VALUES ('short_interest_finra', 'PENDING', NOW(), NULL, NULL, NULL)
ON CONFLICT (table_name) DO NOTHING;
