-- Migration 1020: Create company_info_sec table
-- Purpose: Replace yfinance company info with SEC EDGAR master data
-- Date: 2026-07-18
-- Effort: Phase 3 of data source optimization (reduces yfinance dependency by ~15%)

-- Table: company_info_sec
-- Company master data from SEC EDGAR submissions API.
-- Official entity name, SIC code, sector classification, shares outstanding.
-- Annual updates (company info changes rarely).
-- One row per symbol per update date.
CREATE TABLE IF NOT EXISTS company_info_sec (
    symbol VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,

    entity_name VARCHAR(255),                        -- Official company name from SEC
    sic_code INT,                                    -- Standard Industrial Classification code
    sic_description VARCHAR(255),                    -- SIC sector description
    entity_type VARCHAR(50),                         -- e.g., "large accelerated filer", "other"

    shares_outstanding BIGINT,                       -- Common shares outstanding (from DEI)

    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (symbol, filing_date)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_company_info_sec_filing_date
    ON company_info_sec(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_company_info_sec_unavailable
    ON company_info_sec(data_unavailable);
CREATE INDEX IF NOT EXISTS idx_company_info_sec_symbol
    ON company_info_sec(symbol);

-- Comment
COMMENT ON TABLE company_info_sec IS 'Company master data from SEC EDGAR submissions endpoint. Replaces yfinance company info fields (sector, industry, exchange, entity name). SEC data is authoritative source for company classification.';
COMMENT ON COLUMN company_info_sec.entity_name IS 'Official company name from SEC EDGAR (e.g., "Apple Inc.")';
COMMENT ON COLUMN company_info_sec.sic_code IS 'Standard Industrial Classification code (4-digit SIC code)';
COMMENT ON COLUMN company_info_sec.sic_description IS 'Human-readable SIC sector description';
COMMENT ON COLUMN company_info_sec.entity_type IS 'SEC entity type (e.g., large accelerated filer, accelerated filer, non-accelerated filer)';
COMMENT ON COLUMN company_info_sec.shares_outstanding IS 'Number of common shares outstanding (from DEI facts, typically from latest 10-Q)';
COMMENT ON COLUMN company_info_sec.filing_date IS 'Date when this company info was retrieved (annual updates)';

-- Initial loader status for data_loader_status tracking
INSERT INTO data_loader_status (table_name, status, last_updated, execution_started, execution_completed, error_message)
VALUES ('company_info_sec', 'PENDING', NOW(), NULL, NULL, NULL)
ON CONFLICT (table_name) DO NOTHING;
