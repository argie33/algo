-- Migration 1021: Create earnings_calendar_sec table
-- Purpose: Replace yfinance earnings dates with SEC EDGAR filing dates
-- Date: 2026-07-18
-- Effort: Phase 3 of data source optimization (reduces yfinance dependency by ~10%)

-- Table: earnings_calendar_sec
-- Earnings announcement dates from SEC EDGAR 10-K (annual) and 10-Q (quarterly) filings.
-- Official filing dates when earnings are announced to SEC.
-- Continuous updates (quarterly and annual filings).
-- One row per filing (10-K or 10-Q).
CREATE TABLE IF NOT EXISTS earnings_calendar_sec (
    symbol VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,

    filing_type VARCHAR(20),                         -- "10-K" or "10-Q"

    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (symbol, filing_date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_sec_filing_date
    ON earnings_calendar_sec(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_sec_unavailable
    ON earnings_calendar_sec(data_unavailable);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_sec_symbol
    ON earnings_calendar_sec(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_sec_filing_type
    ON earnings_calendar_sec(filing_type);

-- Comment
COMMENT ON TABLE earnings_calendar_sec IS 'Earnings announcement dates from SEC EDGAR 10-K (annual) and 10-Q (quarterly) filings. Replaces yfinance earnings_date field. SEC filing dates are authoritative source for when earnings are officially announced to regulators.';
COMMENT ON COLUMN earnings_calendar_sec.filing_type IS 'Type of filing: "10-K" for annual report or "10-Q" for quarterly report';
COMMENT ON COLUMN earnings_calendar_sec.filing_date IS 'Date when 10-K/10-Q was filed with SEC (earnings announcement date)';

-- Initial loader status for data_loader_status tracking
INSERT INTO data_loader_status (table_name, status, last_updated, execution_started, execution_completed, error_message)
VALUES ('earnings_calendar_sec', 'PENDING', NOW(), NULL, NULL, NULL)
ON CONFLICT (table_name) DO NOTHING;
