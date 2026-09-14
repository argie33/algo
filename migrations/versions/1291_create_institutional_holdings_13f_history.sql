-- Migration 1291: Create institutional_holdings_13f_history.
--
-- ADDED 2026-09-14 (scores-input data-depth investigation): institutional_holdings_13f's
-- primary key is `symbol` alone (a single current-snapshot upsert table by design - every
-- regular run's fetch_global() overwrites each symbol's one row with whatever quarter's
-- bulk dataset it just parsed). That's the right shape for the loader's real job (give
-- stock_scores/the dashboard the latest ownership %), but it structurally CANNOT hold a
-- quarter-over-quarter time series - live-confirmed AAPL has exactly 1 row regardless of
-- how many historical quarters have been processed across past runs.
--
-- This is a SEPARATE, additive table for a different purpose: giving research/backtest
-- code (Fama-MacBeth factor testing) real historical depth to test institutional-ownership
-- candidates against, something the single-snapshot production table was never able to
-- provide. Does not touch institutional_holdings_13f or InstitutionalHoldings13FLoader's
-- regular fetch_global()/run() path at all - that keeps working exactly as before, still
-- the source of truth for "current" ownership %.
--
-- Populated by scripts/backfill_institutional_holdings_13f_history.py, which iterates
-- every historical SEC 13F bulk dataset (not just the latest, like the regular loader)
-- and reuses InstitutionalHoldings13FLoader's own parsing/crosswalk logic so historical
-- rows are computed identically to how the production table's snapshot is computed each
-- quarter - same ownership_pct math, same >100% capping/flagging, same
-- shares_outstanding sourcing.
CREATE TABLE IF NOT EXISTS institutional_holdings_13f_history (
    symbol VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,
    institutional_ownership_pct NUMERIC(6, 2),
    number_of_institutional_holders INTEGER,
    top_10_institutions_pct NUMERIC(6, 2),
    data_unavailable BOOLEAN NOT NULL DEFAULT FALSE,
    reason VARCHAR(100),
    data_source VARCHAR(30) NOT NULL DEFAULT 'sec_form13f_bulk_backfill',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, filing_date)
);

CREATE INDEX IF NOT EXISTS idx_institutional_holdings_13f_history_filing_date
    ON institutional_holdings_13f_history(filing_date);
