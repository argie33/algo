-- Migration 1290: Seed max_positions_per_sector_real_estate into algo_config
--
-- ISSUE (/goal session, 2026-09-11): the generic max_positions_per_sector gate
-- (entry-side phase8_entry_execution.py, exit-side backstop phase6_exit_execution.py) is
-- a flat 8-of-20 (40%) ceiling. Live leaderboard pull this session found Real Estate at
-- 14% of the top-50 (production-equivalent filter: composite_score > 0, data_completeness
-- >= 70, not data_unavailable, market_cap >= $300M, avg_dollar_volume_20d >= $500K) -
-- confirmed overweighted AND underperforming (21-day forward return -0.63% median vs
-- +0.35% rest-of-universe, 730-day trailing window - see
-- reit_risk_pillar_concentration_not_fixable_by_sector_relative_20260911 in memory).
--
-- Three independent scoring-math fixes were tested and rejected before this: sector-neutral
-- rescaling of the Risk pillar's volatility curve (fails on Spearman IC math invariance -
-- risk_pillar_sector_relative_volatility_rejected_20260911), a leverage-based risk
-- substitute (not era-robust, sign disagreement between regression and raw IC -
-- reit_leverage_vs_volatility_risk_predictor_rejected_20260911), and a per-sector
-- reliability-shrinkage of the Risk pillar's composite contribution (shrink-map too noisy
-- off only ~55 fit-era months - risk_pillar_sector_reliability_shrinkage_rejected_20260911).
-- The problem cannot be fixed at the scoring-math layer with the data currently available.
--
-- This is a portfolio-construction fix instead: a tighter, sector-specific override on the
-- existing generic sector-concentration gate (sector_position_cap() in
-- algo/orchestrator/type_converters.py), leaving the global max_positions_per_sector=8
-- untouched so Financial Services' confirmed-DESERVED overweighting
-- (financial_services_pillar_concentration_deserved_not_artifact_20260911: +0.64% vs
-- +0.31% forward returns, genuine outperformance) is not constrained by the same change.
--
-- Value of 2: Real Estate's observed 14% share of a 20-position portfolio scales to ~2.8
-- positions; capping at 2 meaningfully reduces (not eliminates) exposure to a sector with
-- a confirmed-underperforming, confirmed-unreliable (weakest/only-statistically-insignificant
-- Risk-factor IC of every sector tested, t=1.53) Risk-pillar signal, without being a
-- de-facto exclusion (0 or 1 would functionally remove the sector from the strategy
-- entirely, which the evidence gathered does not support - REITs are underperforming
-- while overweighted, not proven to have zero standalone value).
--
-- Fails closed if unset or malformed: sector_position_cap() falls back to the existing
-- global max_positions_per_sector for every sector, Real Estate included, if this key is
-- ever missing or fails int conversion - this migration only tightens, it introduces no
-- new failure mode in either phase6 or phase8's existing fail-open/fail-fast handling
-- around the global cap.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('max_positions_per_sector_real_estate', '2', 'int',
        'Sector-specific override of max_positions_per_sector for Real Estate only - confirmed overweighted+underperforming via Risk pillar (see reit_risk_pillar_concentration_not_fixable_by_sector_relative_20260911 in memory), not fixable at the scoring-math layer after 3 rejected attempts. Falls back to the global max_positions_per_sector if unset/malformed.',
        'migration-1290')
ON CONFLICT (key) DO NOTHING;
