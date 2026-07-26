-- Migration 1157: Create sec_segment_info table for XBRL segment disclosure data
--
-- Purpose: Stores parsed business segment data from SEC 10-K/10-Q XBRL filings (ASC 280)
-- This is the source table for load_sec_segment_metrics.py, which computes diversification metrics
-- Data populated by XBRL segment parser from SEC EDGAR companyfacts API

CREATE TABLE IF NOT EXISTS sec_segment_info (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_period VARCHAR NOT NULL,  -- "FY" for annual (10-K), "Q1"/"Q2"/"Q3" for quarterly (10-Q)
    filing_date DATE NOT NULL,

    -- Segment disclosure structure
    segment_count INTEGER,  -- Total number of reportable segments
    segment_type VARCHAR,  -- 'operating', 'geographic', 'product', 'customer'
    segment_name VARCHAR,
    segment_revenue NUMERIC(15, 2),  -- Revenue by segment
    segment_operating_income NUMERIC(15, 2),
    segment_assets NUMERIC(15, 2),

    -- Aggregate metrics (computed from all segments)
    largest_segment_revenue_pct NUMERIC(5, 2),  -- % of total from largest segment (0-100)
    revenue_concentration_hhi NUMERIC(5, 3),  -- Herfindahl index (0-10000, 10000=monopoly)
    segment_data_available BOOLEAN DEFAULT FALSE,

    -- Data quality tracking
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR,  -- Why data unavailable (e.g. "single_segment", "no_segment_disclosure")

    -- Audit trail
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    parsed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(symbol, fiscal_year, fiscal_period, segment_name)
);

CREATE INDEX idx_sec_segment_info_symbol ON sec_segment_info(symbol);
CREATE INDEX idx_sec_segment_info_fiscal_year ON sec_segment_info(fiscal_year);
CREATE INDEX idx_sec_segment_info_segment_type ON sec_segment_info(segment_type);

-- Add to data_loader_status tracking
INSERT INTO data_loader_status (table_name, completion_pct, last_updated)
VALUES ('sec_segment_info', 0.0, NOW())
ON CONFLICT (table_name) DO UPDATE
SET last_updated = NOW();
