-- Migration 1024: Fix short_interest_finra.data_source default and stale comment
-- Purpose: Session 298 replaced the broken FINRA CSV endpoint with the real FINRA
-- Consolidated Short Interest Query API (api.finra.org). The column default and
-- comment still said "yfinance_api" from an earlier fallback design that was never
-- actually shipped to production. Fix the default going forward; existing NULL/stale
-- rows will be corrected on the next loader run (which now always sets data_source).

ALTER TABLE IF EXISTS short_interest_finra
ALTER COLUMN data_source SET DEFAULT 'finra_query_api';

COMMENT ON COLUMN short_interest_finra.data_source IS
    'Always "finra_query_api" (FINRA Consolidated Short Interest Query API, api.finra.org). short_pct is computed from FINRA short_shares / company_info_sec.shares_outstanding.';
