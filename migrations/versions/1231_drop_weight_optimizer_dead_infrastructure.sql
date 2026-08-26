-- Migration 1231: Drop WeightOptimizer's dead tables and swing_weight_* config keys
--
-- DECISION: WeightOptimizer (algo/orchestration/weight_optimizer.py, invoked every Phase 9
-- reconciliation) has been a guaranteed permanent no-op since 2026-06-17 - its IC source
-- (SignalAttributionEngine.compute_ic()) was deprecated when swing_trader_scores was removed
-- in the swing_trader_scores -> composite_score migration, and unconditionally returns
-- sample_size=0 ever since (confirmed: algo_weight_history has exactly 14 rows, all dated
-- 2026-06-17, nothing since, despite 2,709+ Phase 9 runs). Confirmed via a fresh full-repo
-- grep (2026-08-26) that the swing_weight_* config keys these components fed are consumed
-- ONLY by WeightOptimizer/SignalAttributionEngine/tests/migrations themselves - no live
-- stock_scores/signal_quality_score/composite path reads them. Removed together with the
-- Python code (algo/orchestration/weight_optimizer.py, algo/signals/attribution.py) and
-- their Phase 9 call sites, per the "remove together, not piecemeal" guidance already
-- recorded when this gap was first flagged.
--
-- Does NOT touch swing_min_trend_score/swing_min_industry_rank/swing_days_to_earnings_block/
-- swing_grade_threshold_*/advanced_filters_grade_threshold_* - those are a different, still-
-- live "swing trader" grading/filtering system unrelated to WeightOptimizer's component
-- weights, confirmed by name (COMPONENT_KEYS only ever mapped to the 7 swing_weight_* keys
-- below) and left untouched.

DELETE FROM algo_config WHERE key IN (
    'swing_weight_setup',
    'swing_weight_trend',
    'swing_weight_momentum',
    'swing_weight_volume',
    'swing_weight_fundamentals',
    'swing_weight_sector',
    'swing_weight_multi_timeframe'
);

DROP TABLE IF EXISTS algo_weight_history;
DROP TABLE IF EXISTS algo_component_attribution;
DROP TABLE IF EXISTS algo_information_coefficient;
