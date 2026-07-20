-- Migration 1022: Add data_source tracking to all metric and enrichment tables
-- Purpose: Track which data source provided each data point for reproducibility, debugging, and transparency
-- Date: 2026-07-18
-- Impact: 13 tables affected (metrics, enrichment, score tables)

-- ============================================================================
-- METRIC TABLES
-- ============================================================================

ALTER TABLE IF EXISTS value_metrics
ADD COLUMN data_source VARCHAR(100) DEFAULT NULL;

ALTER TABLE IF EXISTS quality_metrics
ADD COLUMN data_source VARCHAR(100) DEFAULT NULL;

ALTER TABLE IF EXISTS growth_metrics
ADD COLUMN data_source VARCHAR(100) DEFAULT NULL;

ALTER TABLE IF EXISTS positioning_metrics
ADD COLUMN data_source VARCHAR(100) DEFAULT NULL;

ALTER TABLE IF EXISTS stability_metrics
ADD COLUMN data_source VARCHAR(100) DEFAULT NULL;

-- ============================================================================
-- ENRICHMENT TABLES (SEC and FINRA data)
-- ============================================================================

ALTER TABLE IF EXISTS short_interest_finra
ADD COLUMN data_source VARCHAR(100) DEFAULT 'yfinance_api';

ALTER TABLE IF EXISTS company_info_sec
ADD COLUMN data_source VARCHAR(100) DEFAULT 'sec_edgar_submissions';

ALTER TABLE IF EXISTS earnings_calendar_sec
ADD COLUMN data_source VARCHAR(100) DEFAULT 'sec_edgar_filings';

ALTER TABLE IF EXISTS institutional_holdings_13f
ADD COLUMN data_source VARCHAR(100) DEFAULT 'sec_13f';

ALTER TABLE IF EXISTS insider_holdings_sec
ADD COLUMN data_source VARCHAR(100) DEFAULT 'sec_form4';

-- ============================================================================
-- MARKET DATA TABLES
-- ============================================================================

ALTER TABLE IF EXISTS sector_ranking
ADD COLUMN data_source VARCHAR(100) DEFAULT 'price_daily_aggregated';

ALTER TABLE IF EXISTS industry_ranking
ADD COLUMN data_source VARCHAR(100) DEFAULT 'price_daily_aggregated';

-- ============================================================================
-- SCORE TABLES
-- ============================================================================

ALTER TABLE IF EXISTS stock_scores
ADD COLUMN data_sources JSONB DEFAULT NULL;

-- ============================================================================
-- CREATE INDEXES FOR DATA SOURCE TRACKING
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_value_metrics_data_source
    ON value_metrics(data_source);

CREATE INDEX IF NOT EXISTS idx_quality_metrics_data_source
    ON quality_metrics(data_source);

CREATE INDEX IF NOT EXISTS idx_growth_metrics_data_source
    ON growth_metrics(data_source);

CREATE INDEX IF NOT EXISTS idx_positioning_metrics_data_source
    ON positioning_metrics(data_source);

CREATE INDEX IF NOT EXISTS idx_stability_metrics_data_source
    ON stability_metrics(data_source);

CREATE INDEX IF NOT EXISTS idx_short_interest_finra_data_source
    ON short_interest_finra(data_source);

CREATE INDEX IF NOT EXISTS idx_company_info_sec_data_source
    ON company_info_sec(data_source);

CREATE INDEX IF NOT EXISTS idx_earnings_calendar_sec_data_source
    ON earnings_calendar_sec(data_source);

CREATE INDEX IF NOT EXISTS idx_institutional_holdings_13f_data_source
    ON institutional_holdings_13f(data_source);

CREATE INDEX IF NOT EXISTS idx_insider_holdings_sec_data_source
    ON insider_holdings_sec(data_source);

CREATE INDEX IF NOT EXISTS idx_sector_ranking_data_source
    ON sector_ranking(data_source);

CREATE INDEX IF NOT EXISTS idx_industry_ranking_data_source
    ON industry_ranking(data_source);

-- ============================================================================
-- COMMENTS DOCUMENTING DATA SOURCE TRACKING
-- ============================================================================

COMMENT ON COLUMN value_metrics.data_source IS 'Source providing the valuation data: "sec_audited" (from SEC financial statements) or "yfinance_snapshot"';

COMMENT ON COLUMN quality_metrics.data_source IS 'Source providing the quality metrics: "sec_audited" (from SEC financial statements only; no yfinance fallback)';

COMMENT ON COLUMN growth_metrics.data_source IS 'Source providing growth rates: "sec_audited" (from SEC financial statements only)';

COMMENT ON COLUMN positioning_metrics.data_source IS 'Source of holdings data: "sec_13f" (institutional), "sec_form4" (insider), or "yfinance_api" (fallback)';

COMMENT ON COLUMN stability_metrics.data_source IS 'Source providing stability metrics: "yfinance_api" or "computed_from_price_daily"';

COMMENT ON COLUMN short_interest_finra.data_source IS 'Always "yfinance_api" (FINRA data via yfinance aggregator)';

COMMENT ON COLUMN company_info_sec.data_source IS 'Always "sec_edgar_submissions" (SEC EDGAR submissions API)';

COMMENT ON COLUMN earnings_calendar_sec.data_source IS 'Always "sec_edgar_filings" (SEC EDGAR filing dates)';

COMMENT ON COLUMN institutional_holdings_13f.data_source IS 'Always "sec_13f" (SEC Form 13F filings)';

COMMENT ON COLUMN insider_holdings_sec.data_source IS 'Always "sec_form4" (SEC Form 4/5 filings)';

COMMENT ON COLUMN sector_ranking.data_source IS 'Always "price_daily_aggregated" (computed from price_daily table)';

COMMENT ON COLUMN industry_ranking.data_source IS 'Always "price_daily_aggregated" (computed from price_daily table)';

COMMENT ON COLUMN stock_scores.data_sources IS 'JSON map of metric_name -> source for transparency: {value: "sec_audited", quality: "sec_audited", growth: "sec_audited", positioning: "sec_13f", stability: "yfinance_api"}';

-- ============================================================================
-- BACKFILL DATA SOURCES FOR ENRICHMENT TABLES (with defaults since they have fixed sources)
-- ============================================================================

UPDATE short_interest_finra
SET data_source = 'yfinance_api'
WHERE data_source IS NULL;

UPDATE company_info_sec
SET data_source = 'sec_edgar_submissions'
WHERE data_source IS NULL;

UPDATE earnings_calendar_sec
SET data_source = 'sec_edgar_filings'
WHERE data_source IS NULL;

UPDATE institutional_holdings_13f
SET data_source = 'sec_13f'
WHERE data_source IS NULL;

UPDATE insider_holdings_sec
SET data_source = 'sec_form4'
WHERE data_source IS NULL;

UPDATE sector_ranking
SET data_source = 'price_daily_aggregated'
WHERE data_source IS NULL;

UPDATE industry_ranking
SET data_source = 'price_daily_aggregated'
WHERE data_source IS NULL;
