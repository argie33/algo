-- Migration 1243: Add net_payout_yield (dividends + buybacks) to sec_valuations and value_metrics
-- Date: 2026-08-27
-- (Originally authored as migration 1236 on the worktree-size-factor-promotion branch, before
-- main had claimed that number for a different migration - "add_extended_quality_factor_inputs".
-- By the time this work was ported to main, 1236 through 1242 were all taken (1242 =
-- add_book_value_growth_to_growth_metrics, main's highest real migration at port time), so this
-- is renumbered to 1243 - same class of collision as migration 1146's own header comment and as
-- 1234->1236's own renumbering noted below.)
-- (That original numbering was itself 1236, not 1234 - 1234 was claimed concurrently by another
-- session's "add_retained_earnings_to_annual_balance_sheet" migration; renumbered at the time to
-- avoid that collision, same class of issue documented in migration 1146's own header comment.)

-- ROOT CAUSE: the Value pillar's dividend_yield input (load_stock_scores.py._score_value) only
-- captures cash returned to shareholders via dividends. Real SEC XBRL buyback data
-- (annual_cash_flow.common_stock_repurchased, migration 1206, "PaymentsForRepurchaseOfCommonStock")
-- has been loaded since 2026-07 but never consumed by any downstream valuation/scoring path.
-- This is exactly the gap the "total payout yield" literature (Boudoukh, Michaely, Richardson,
-- Roberts 2007) and O'Shaughnessy's "Shareholder Yield" screen argue matters: most large-cap US
-- firms have shifted a meaningful share of shareholder returns from dividends to buybacks since
-- the 1980s, so dividend-only payout understates true capital return and is a noisier/weaker
-- signal than the combined measure. Confirmed directly in this system's own Fama-MacBeth
-- validation (algo/research/fama_macbeth_value_factors.py, 2026-08-26 CANDIDATE CHECK):
-- net_payout_yield univariate t=3.27, multivariate t=3.05 (jointly with the live 8 Value
-- inputs) - both stronger than dividend_yield's own t=1.55-2.28, and dividend_yield's own
-- multivariate coefficient FLIPS to negative/insignificant once net_payout_yield is present,
-- meaning dividend_yield's positive univariate signal was actually payout information now
-- better captured by the combined measure.
--
-- Fix: adds net_payout_yield = (dividends_paid + common_stock_repurchased) / market_cap to
-- sec_valuations (computed alongside dividend_yield in load_sec_valuations.py, same
-- dual-class/entity-wide-market-cap treatment dividend_yield already has) and mirrors it to
-- value_metrics (populated by load_value_quality_growth_metrics.py). dividend_yield itself is
-- UNCHANGED and stays computed/stored/displayed - net_payout_yield REPLACES it only in Value
-- scoring's weighted formula (see load_stock_scores.py._score_value), same "computed but no
-- longer scoring-consumed" convention already used for ev_ebitda/ev_revenue/amihud_illiquidity.

BEGIN;

ALTER TABLE sec_valuations ADD COLUMN IF NOT EXISTS net_payout_yield NUMERIC;
ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS net_payout_yield NUMERIC;

COMMENT ON COLUMN sec_valuations.net_payout_yield IS
    '(dividends_paid + common_stock_repurchased) / entity-wide market_cap, decimal fraction (0.03 = 3%) - same convention as dividend_yield. "Total payout yield" (Boudoukh/Michaely/Richardson/Roberts 2007) / "Shareholder Yield" (O''Shaughnessy) - captures buybacks alongside dividends, which dividend_yield alone misses.';
COMMENT ON COLUMN value_metrics.net_payout_yield IS
    'Mirrors sec_valuations.net_payout_yield, with a TIER 2 fallback computed directly from annual_cash_flow (dividends_paid + common_stock_repurchased) / market_cap when sec_valuations has no row - same fallback pattern as dividend_yield''s TIER 3. Live Value scoring input (load_stock_scores.py._score_value) - replaces dividend_yield in the weighted formula.';

COMMIT;
