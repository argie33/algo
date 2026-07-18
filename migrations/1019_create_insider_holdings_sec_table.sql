-- Migration 1019: Create insider_holdings_sec table
-- Purpose: Replace yfinance held_percent_insiders with SEC Form 4/5 insider holdings
-- Date: 2026-07-18
-- Effort: Phase 2 of data source optimization (reduces yfinance dependency by ~15%)

-- Table: insider_holdings_sec
-- Near real-time insider ownership data from SEC Form 4/5 filings (2-day lag).
-- Form 4 is filed within 2 days of insider transactions (officers, directors, 10%+ owners).
-- Form 5 is filed annually for remaining insider holdings.
-- Updated continuously as insiders trade (2-day regulatory lag).
-- One row per symbol per reporting date.
CREATE TABLE IF NOT EXISTS insider_holdings_sec (
    symbol VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,

    insider_ownership_pct DECIMAL(6, 2),            -- Insider ownership % (aggregated from Form 4/5)
    number_of_insiders INT,                         -- Count of distinct insiders (officers, directors, 10%+ owners)

    recent_buys INT,                                -- Number of insider buy transactions in last 30 days
    recent_sells INT,                               -- Number of insider sell transactions in last 30 days
    net_insider_transactions INT,                   -- Buys minus sells (positive = accumulation)

    latest_insider_filing_date DATE,                -- Most recent Form 4/5 filing date
    sec_filing_url VARCHAR(500),                    -- Link to SEC EDGAR filings

    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (symbol, filing_date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_insider_holdings_sec_filing_date
    ON insider_holdings_sec(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_insider_holdings_sec_unavailable
    ON insider_holdings_sec(data_unavailable);
CREATE INDEX IF NOT EXISTS idx_insider_holdings_sec_symbol
    ON insider_holdings_sec(symbol);

-- Comment
COMMENT ON TABLE insider_holdings_sec IS 'Near real-time insider ownership data from SEC Form 4/5 filings. Replaces yfinance held_percent_insiders. Form 4 filed within 2 days of insider transactions; Form 5 filed annually. More granular than yfinance (see exact transactions, not just %).';
COMMENT ON COLUMN insider_holdings_sec.insider_ownership_pct IS 'Percentage of shares held by insiders (officers, directors, 10%+ owners, 0-100)';
COMMENT ON COLUMN insider_holdings_sec.number_of_insiders IS 'Count of distinct insiders tracked (from latest Form 4/5 filings)';
COMMENT ON COLUMN insider_holdings_sec.recent_buys IS 'Count of insider buy transactions in last 30 days (signal of management confidence)';
COMMENT ON COLUMN insider_holdings_sec.recent_sells IS 'Count of insider sell transactions in last 30 days';
COMMENT ON COLUMN insider_holdings_sec.net_insider_transactions IS 'Recent buys minus recent sells (positive = accumulation = bullish signal)';
COMMENT ON COLUMN insider_holdings_sec.filing_date IS 'Date of the Form 4/5 filing (continuous; within 2 days of transaction)';
COMMENT ON COLUMN insider_holdings_sec.latest_insider_filing_date IS 'Latest available Form 4/5 filing date (tracks data freshness)';
COMMENT ON COLUMN insider_holdings_sec.sec_filing_url IS 'Direct link to SEC EDGAR filings for verification';

-- Initial loader status for data_loader_status tracking
INSERT INTO data_loader_status (table_name, status, last_updated, execution_started, execution_completed, error_message)
VALUES ('insider_holdings_sec', 'PENDING', NOW(), NULL, NULL, NULL)
ON CONFLICT (table_name) DO NOTHING;
