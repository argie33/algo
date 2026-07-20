-- Migration 1018: Create institutional_holdings_13f table
-- Purpose: Replace yfinance held_percent_institutions with SEC Form 13F institutional holdings
-- Date: 2026-07-18
-- Effort: Phase 2 of data source optimization (reduces yfinance dependency by ~20%)

-- Table: institutional_holdings_13f
-- Quarterly institutional ownership data from SEC Form 13F filings (audited, authoritative).
-- Form 13F is filed by institutional investment managers with $100M+ in assets.
-- Updated quarterly (90-day lag acceptable for stock scoring).
-- One row per symbol per filing date.
CREATE TABLE IF NOT EXISTS institutional_holdings_13f (
    symbol VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,

    institutional_ownership_pct DECIMAL(6, 2),      -- Institutional ownership % (aggregated from 13F holders)
    number_of_institutional_holders INT,             -- Count of distinct institutional holders

    sec_filing_url VARCHAR(500),                     -- Link to SEC EDGAR filing
    most_recent_filing_date DATE,                    -- Latest available 13F filing for this symbol

    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (symbol, filing_date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_institutional_holdings_13f_filing_date
    ON institutional_holdings_13f(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_institutional_holdings_13f_unavailable
    ON institutional_holdings_13f(data_unavailable);
CREATE INDEX IF NOT EXISTS idx_institutional_holdings_13f_symbol
    ON institutional_holdings_13f(symbol);

-- Comment
COMMENT ON TABLE institutional_holdings_13f IS 'Quarterly institutional ownership data from SEC Form 13F filings. Replaces yfinance held_percent_institutions. Form 13F is audited, authoritative data from institutional managers with $100M+ in assets.';
COMMENT ON COLUMN institutional_holdings_13f.institutional_ownership_pct IS 'Percentage of shares held by institutional investors (aggregated from 13F holders, 0-100)';
COMMENT ON COLUMN institutional_holdings_13f.number_of_institutional_holders IS 'Count of distinct institutional holders from latest 13F filing';
COMMENT ON COLUMN institutional_holdings_13f.filing_date IS 'Date of the Form 13F filing (quarterly: Q1, Q2, Q3, Q4)';
COMMENT ON COLUMN institutional_holdings_13f.sec_filing_url IS 'Direct link to SEC EDGAR filing for verification';
COMMENT ON COLUMN institutional_holdings_13f.most_recent_filing_date IS 'Latest available 13F filing date (tracks data freshness)';

-- Initial loader status for data_loader_status tracking
INSERT INTO data_loader_status (table_name, status, last_updated, execution_started, execution_completed, error_message)
VALUES ('institutional_holdings_13f', 'PENDING', NOW(), NULL, NULL, NULL)
ON CONFLICT (table_name) DO NOTHING;
