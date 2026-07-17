-- Migration 1011: Create sec_valuations table for audited valuations from SEC data
-- Purpose: Replace yfinance quoteSummary with computed PE/PB/PS/PEG/FCF from SEC filings
-- Date: 2026-07-17
-- Effort: Phase 1 of data source optimization (reduces yfinance dependency)

-- Table: sec_valuations
-- Key metrics computed from SEC financial data (income statement, balance sheet, cash flow)
-- + current stock price (price_daily)
-- One row per symbol per computation run
-- Data quality: Audited SEC data + daily price updates
CREATE TABLE IF NOT EXISTS sec_valuations (
    symbol VARCHAR(20) PRIMARY KEY,
    computed_at DATE NOT NULL,
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),

    -- Price-based metrics
    current_price DECIMAL(10, 2),
    shares_outstanding DECIMAL(15, 0),
    market_cap DECIMAL(20, 2),

    -- Valuation ratios (computed from SEC + price)
    pe_ratio DECIMAL(8, 2),          -- Price / TTM EPS
    pb_ratio DECIMAL(8, 2),          -- Price / Book Value Per Share
    ps_ratio DECIMAL(8, 2),          -- Price / Revenue Per Share
    peg_ratio DECIMAL(8, 2),         -- PE / Earnings Growth Rate %
    fcf_yield DECIMAL(6, 2),         -- (Operating CF - Capex) / Market Cap * 100

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sec_valuations_date ON sec_valuations(computed_at);
CREATE INDEX IF NOT EXISTS idx_sec_valuations_unavailable ON sec_valuations(data_unavailable);

-- Comment
COMMENT ON TABLE sec_valuations IS 'Audited valuations computed from SEC financial data. Replaces yfinance quoteSummary for PE/PB/PS/PEG/FCF. Updated daily post-market.';
COMMENT ON COLUMN sec_valuations.pe_ratio IS 'Price/Earnings: Current Price / TTM EPS from SEC income statement';
COMMENT ON COLUMN sec_valuations.pb_ratio IS 'Price/Book: Current Price / (Book Value / Shares Outstanding) from SEC balance sheet';
COMMENT ON COLUMN sec_valuations.ps_ratio IS 'Price/Sales: Current Price / (TTM Revenue / Shares Outstanding) from SEC income statement';
COMMENT ON COLUMN sec_valuations.peg_ratio IS 'PEG: PE Ratio / Earnings Growth Rate (approximate, from available quarterly data)';
COMMENT ON COLUMN sec_valuations.fcf_yield IS 'Free Cash Flow Yield: ((Operating CF - Capex) / Market Cap) * 100, from SEC cash flow statement';

-- Initial loader status for data_loader_status tracking
INSERT INTO data_loader_status (table_name, status, last_updated, execution_started, execution_completed, error_message)
VALUES ('sec_valuations', 'PENDING', NOW(), NULL, NULL, NULL)
ON CONFLICT (table_name) DO NOTHING;
