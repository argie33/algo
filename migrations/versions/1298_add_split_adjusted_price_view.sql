-- Migration 1298: Add price_daily_split_adjusted view (read-time split adjustment)
--
-- ISSUE: `stock_splits` was a completely dead table (zero rows) until 2026-09-15's
-- fix_missing_stock_splits.py started backfilling it. That script's only remediation
-- method was retroactively MUTATING price_daily's raw OHLC/volume in place per
-- confirmed split - live-caught the same day: a re-run bug double-applied a split's
-- multiplier to already-adjusted rows (had to be algebraically reverse-engineered
-- back out using a pre-change backup), and the approach requires re-doing that exact
-- risky mutation for every one of the ~1,200+ symbols a full-history rescan found
-- with real unrecorded splits (33% confirmed-real hit rate on the first 100 of 3,751
-- candidates checked against yfinance ground truth). At that volume, retroactive
-- in-place mutation is not a safe pattern to keep repeating.
--
-- INDUSTRY PATTERN (verified against CRSP - the academic/institutional reference
-- dataset most quant research is built on - plus QuantConnect/LEAN and Zipline):
-- raw OHLCV is stored permanently unchanged; a separate cumulative adjustment
-- factor (CRSP's CFACPR) is maintained from the corporate-actions table, and
-- adjusted price = raw price * cumulative factor, computed at READ time, never by
-- mutating the raw store. A mistake in the adjustment factor means fixing one row
-- in a small table, not un-mutating millions of price rows.
--
-- FIX: price_daily itself goes back to being treated as permanently raw/immutable
-- going forward (FXHO/ABTC/FFAI's earlier in-place mutations were undone the same
-- day by replacing their history with a fresh raw pull from Alpaca, specifically so
-- this view's math is never double-applying an adjustment already baked into the
-- raw columns). This view computes split-adjusted OHLCV+volume on the fly from
-- price_daily joined against stock_splits - as more splits get confirmed and
-- inserted into stock_splits, every consumer of this view is correct immediately,
-- with zero risk of a mutation bug, and zero backfill required.
--
-- Cumulative factor = product of (1/split_ratio) for every split strictly after a
-- given row's date (yfinance's ratio convention: new/old shares, e.g. 0.2 for a
-- 1-for-5 reverse split, 2.0 for a 2-for-1 forward split - matches
-- fix_missing_stock_splits.py's own adjust_factor = 1/ratio). No PRODUCT()
-- aggregate exists in Postgres, so EXP(SUM(LN(x))) computes the same cumulative
-- product; ratios are always positive (checked - schema/loader never allows <= 0),
-- so LN is always defined. Volume moves the opposite direction of price (more
-- shares outstanding after a forward split), so it's divided by the same factor
-- price is multiplied by.

-- CORRECTED same day, before this went live anywhere (caught testing against AAPL's
-- real 2020 4-for-1 split): yfinance's `close` is NOT raw the way this migration's
-- header assumed - Yahoo retroactively restates a symbol's ENTIRE close-price history
-- for every split it knows about AS OF THE MOMENT A ROW IS FETCHED, regardless of
-- auto_adjust/adjustment settings (only dividend adjustment is optional; splits are
-- baked into `close` unconditionally, always). AAPL's rows were bulk-loaded
-- 2026-08-25, long after all 5 of its real splits (1987-2020) - so they're already
-- correctly adjusted, and naively multiplying by this view's factor for every split
-- after a row's date double-adjusted them (live-caught: $125.01 on 2020-08-27, already
-- correctly reflecting the 2020-08-31 4-for-1 split, got divided by 4 again into a
-- fake $31.25 with no real discontinuity to justify it).
--
-- The real rule: a row only needs this view's multiplier for a split if the row was
-- fetched BEFORE that split happened (created_at < split_date) - i.e. the vendor
-- genuinely could not have known about it yet at fetch time, and never re-fetches old
-- history afterward (confirmed on ticker ANY: split 2026-02-10, row loaded 2026-05-25
-- - already smooth, no kink, correctly excluded by this condition). Alpaca is the one
-- exception: its `adjustment=raw` mode (deliberately used, see
-- utils/external/alpaca_market_data.py) never restates history for splits regardless
-- of fetch time, so Alpaca-sourced rows always need the multiplier for every
-- applicable split. Measured scope under this corrected rule: 264,704 rows across 853
-- symbols actually need adjustment - not the full 26M-row table.
CREATE VIEW price_daily_split_adjusted AS
SELECT
    pd.id,
    pd.symbol,
    pd.date,
    pd.open,
    pd.high,
    pd.low,
    pd.close,
    pd.volume,
    pd.adj_close,
    pd.data_source,
    (pd.open * f.factor)::numeric(20, 4) AS open_adjusted,
    (pd.high * f.factor)::numeric(20, 4) AS high_adjusted,
    (pd.low * f.factor)::numeric(20, 4) AS low_adjusted,
    (pd.close * f.factor)::numeric(20, 4) AS close_adjusted,
    -- NULL-safe: ~4M price_daily rows have adj_close IS NULL (never backfilled for
    -- those historical loads) - fall back to close like every prior caller of this
    -- pair already did (e.g. load_risk_metrics_daily.py's `row[2] if row[2] is not
    -- None else row[1]` pattern this view's consumers replaced).
    (COALESCE(pd.adj_close, pd.close) * f.factor)::numeric(20, 4) AS adj_close_adjusted,
    ROUND(pd.volume / f.factor) AS volume_adjusted,
    f.factor AS split_adjustment_factor
FROM price_daily pd
CROSS JOIN LATERAL (
    SELECT COALESCE(EXP(SUM(LN(1.0 / ss.split_ratio))), 1.0) AS factor
    FROM stock_splits ss
    WHERE ss.symbol = pd.symbol
      AND ss.split_date > pd.date
      AND (pd.data_source = 'alpaca' OR pd.created_at < ss.split_date)
) f;

COMMENT ON VIEW price_daily_split_adjusted IS
'Read-time split-adjusted prices: raw price_daily * cumulative split factor since that date, sourced from stock_splits. price_daily itself must stay permanently raw/unmutated - see migration 1298 docstring. Recompute is automatic as stock_splits gains rows; no backfill needed.';
