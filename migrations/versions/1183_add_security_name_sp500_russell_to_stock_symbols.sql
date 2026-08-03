-- Migration 1181: Add security_name, is_sp500, is_russell2000 to stock_symbols
--
-- ISSUE: loaders/load_market_constituents.py writes security_name/is_sp500/is_russell2000
-- to stock_symbols (index-constituent enrichment - see its _enrich_with_index_flags step),
-- and lambda/api/routes/scores.py's stock-scores query reads ss.security_name/ss.is_sp500
-- directly - but neither column was ever added as a versioned migration (same
-- "column referenced in code but never tracked" drift class as migrations 062/063, which
-- added stock_symbols.active/is_russell2000 for the same reason). Confirmed live: a local
-- dev database missing these columns 503s on GET /api/scores with
-- `UndefinedColumn: column ss.security_name does not exist`, and
-- load_market_constituents.py would fail the same way writing is_sp500.
--
-- is_russell2000 was already added by migration 063 for load_russell2000_constituents.py -
-- included here defensively (IF NOT EXISTS) since it belongs to the same
-- load_market_constituents.py enrichment step as is_sp500 and a database that's missing one
-- may be missing both.

ALTER TABLE stock_symbols
    ADD COLUMN IF NOT EXISTS security_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS is_sp500 BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_russell2000 BOOLEAN DEFAULT FALSE;

-- Backfill security_name from the existing company_name for rows loaded before this
-- migration - better than leaving a NULL display name for symbols not yet re-touched by
-- load_market_constituents.py.
UPDATE stock_symbols SET security_name = company_name WHERE security_name IS NULL;

COMMENT ON COLUMN stock_symbols.security_name IS
    'Official security name from the market-constituents feed (loaders/load_market_constituents.py) - may differ from company_name (a separate SEC-sourced field). Backfilled from company_name for pre-migration rows.';
COMMENT ON COLUMN stock_symbols.is_sp500 IS
    'S&P 500 constituent flag, set by load_market_constituents.py against the official S&P 500 list.';
COMMENT ON COLUMN stock_symbols.is_russell2000 IS
    'Russell 2000 constituent flag, set by load_market_constituents.py / load_russell2000_constituents.py.';
