-- Migration 1273: Seed use_scale_out_targets=false into algo_config
--
-- ISSUE (exit-strategy literature review + validation backtest, 2026-09-07): the exit chain's
-- T1/T2/T3 partial-profit-taking design (sell 50%/25%/25% at fixed R-multiples) was the one
-- place a prior literature review found trend-following research fairly consistently against
-- the current approach - scaling out lowers blended expectancy vs. a pure trail by capping the
-- fat-tail winners a trend system's edge depends on.
--
-- Validated against our own data (not literature alone - see
-- scripts/backtest_exit_strategy_comparison_20260907.py): a paired backtest replaying the real
-- price-technical BUY entry trigger (algo/signals/buy_signal_generator.py's swing-pivot
-- breakout above a rising 50-day SMA - no fundamentals dependency, replayable decades back)
-- across 2,885 symbols with 10+ years of price_daily history (471,972 paired trades,
-- 1962-2026) found a pure trailing-stop design (chandelier trail + breakeven floor, no
-- scale-out) beat this T1/T2/T3 chain on:
--   - mean R-multiple:            +0.096 vs +0.085
--   - geometric per-trade growth: +0.088% vs +0.079% (at 1% account risk/trade)
--   - tail capture:               57.5% vs 52.7% of total profit from the top decile of trades
--   - paired mean-R difference: -0.0114, 95% bootstrap CI [-0.0132, -0.0096] (excludes zero)
--
-- See algo/trading/exit_position_context.py's check_target_t1 docstring for the gating logic:
-- disabling T1 alone cascades to disable T2/T3 (they only fire once target_hits advances,
-- which only T1/T2 ever set) - the T1/T2/T3 machinery itself is untouched, just gated off.
-- Re-enable by flipping this value back to true if a future backtest finds the opposite on a
-- larger/different sample.
--
-- NOTE: this fix originated as migration 1272 on a stranded worktree branch
-- (worktree-xbrl-concept-continuity-checker) before main independently claimed 1272 for an
-- unrelated fix (data_patrol_log.patrol_date default) - renumbered to 1273 when reconciled
-- onto main, 2026-09-08.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('use_scale_out_targets', 'false', 'bool',
        'Enable T1/T2/T3 partial-exit scale-out - disabled after validation backtest found a pure trail design superior (see exit_position_context.py check_target_t1 docstring)',
        'migration-1273')
ON CONFLICT (key) DO NOTHING;
