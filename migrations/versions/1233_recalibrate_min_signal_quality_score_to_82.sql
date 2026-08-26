-- Migration 1233: Recalibrate min_signal_quality_score from 75 to 82
--
-- 2026-08-26 real-money-readiness review found two things about this live real-money entry
-- gate (Phase 8's min_signal_quality_score) that combine into this recalibration:
--
-- 1. The live value of 75 had an undocumented origin (algo_config.updated_by='test', empty
--    description, changed 2026-08-17) that predates the signal_quality_score formula
--    unification fix (a9671ba8a, landed 2026-08-20) - it could not have been a deliberate
--    calibration against the current formula's distribution. The last properly documented,
--    evidence-based calibration was commit c37adac72 (2026-07-31): "Lowered
--    min_signal_quality_score from 85 to 60 to match actual score distribution... Now 72% of
--    signals qualify instead of 0%... maintains quality filtering while enabling entries."
--
-- 2. A 10-year, 125-independent-month Fama-MacBeth backtest
--    (algo/research/signal_quality_score_historical_backtest.py, 8,131 reconstructed BUY
--    signals, 150 liquid symbols) found volume_confirmation_score (RSI 40-80 + bullish MACD
--    cross) has a STATISTICALLY SIGNIFICANT NEGATIVE correlation with forward returns (5d
--    t=-2.59, 20d t=-2.41) - the opposite of what a quality filter should reward. Excluded
--    from the composite's weighting (loaders/signal_quality_scorer.py's
--    BUY_COMPOSITE_EXCLUDED_COMPONENTS, landed 7977807bb) - still computed/displayed, just
--    not counted toward composite_sqs for BUY.
--
-- Removing that component collapsed the achievable score range sharply UPWARD: median jumped
-- from ~61 (the July 2026 calibration's basis) to 97, because the remaining components
-- (trend_template, market_stage - both largely implied by the entry trigger's own price/trend
-- conditions) score near their ceiling for most triggered signals. Reusing the OLD threshold
-- VALUE (60, or even the undocumented 75) against this NEW distribution would now pass ~99%
-- of signals - a degenerate, non-functional gate. Reusing the raw NUMBER isn't the right
-- carry-forward; reusing the ORIGINAL CALIBRATION'S STATED INTENT (a ~72% pass rate) is.
--
-- Recomputed the corrected composite's distribution against the same 10-year dataset:
-- threshold=82 -> 72.0% pass rate (threshold=84 -> 71.6%, essentially the same; 82 chosen as
-- the cleaner number at a stable point in a heavily discrete distribution - large notches
-- exist at composite_sqs=97 and =100, so the exact threshold matters more than usual here).
--
-- See MEMORY.md signal_quality_score_threshold_recalibrated_20260826 for the full record.
-- config_schema.py's VALIDATION_SCHEMA and config/main.py's DEFAULTS updated to 82 the same
-- day so a fresh environment matches without a manual UPDATE (same gap 1229's own commentary
-- flagged for phase7_min_composite_score - closing it here proactively).

UPDATE algo_config
SET value = '82',
    description = 'Minimum signal_quality_score (0-100) for a signal to qualify for real trade entry in Phase 8 - recalibrated 2026-08-26 to ~72% pass rate against the corrected composite (volume_confirmation excluded), matching the original 2026-07-31 calibration''s target selectivity',
    updated_by = 'migration-1233',
    updated_at = CURRENT_TIMESTAMP
WHERE key = 'min_signal_quality_score'
  AND value IS DISTINCT FROM '82';
