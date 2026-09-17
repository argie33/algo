-- Migration 1294: add market-cap-tilted display weights to stock_scores
--
-- REPLACES the request-time tilt computation duplicated across two API endpoints
-- (lambda/api/routes/algo_handlers/dashboard/scores.py's _apply_market_cap_tilt, merged
-- 2026-09-15 via d9aaae11f/a36dc4223) and a near-third copy that was drafted directly in
-- webapp/frontend/src/pages/ScoresDashboard.jsx before being caught and reverted the same
-- session. Live-caught bug: the Python tilt only ever reached /api/algo/scores - the actual
-- page the user looks at (ScoresDashboard.jsx) calls a completely different endpoint
-- (/api/scores/stockscores) that never got it, so the dashboard kept showing raw-percentile
-- micro/small-cap "leaders" with no cap-weighting for both the Rankings table's sortBy and
-- every one of the 5 per-pillar Leaders/Laggards tabs.
--
-- WHY a stored column instead of computing tilt at request time in N places: real
-- institutional multi-factor index providers (Goldman ActiveBeta, the tractable-to-replicate
-- one of the two funds checked this session - see [[overlap_metric_methodology_clarified_
-- 20260915]] in memory) compute their factor-tilted portfolio construction ONCE on a
-- schedule and publish the result; they do not recompute a live formula on every page view
-- in every consuming surface. Computing once in a batch pass (same pattern as
-- update_momentum_sector_relative_mom_12_1/update_quality_sector_neutral_scores) and storing
-- the result here means every consumer (both API endpoints, the dashboard, any future
-- surface) reads the identical number - structurally impossible for this specific "one path
-- got the fix, the other didn't" bug class to recur.
--
-- NOT a change to composite_score/pillar scores themselves, which stay pure factor-merit and
-- continue to drive live Phase 7/8 trading decisions unchanged - Size was deliberately
-- retired as a scoring PILLAR (2026-08-28, Fama-MacBeth evidence it hurt forward returns) and
-- this does not reverse that. These columns are a DISPLAY/comparison construction only.
-- FORMULA REPLACED 2026-09-16 (user directive: "get rid of all the extra shit beyond ... the
-- industry guys") - the original weight = market_cap * GREATEST(0.1, 1 + k * z_score) with a
-- fitted k=0.2 (chosen by trying values until output matched real LRGF/GSLC holdings overlap)
-- was itself exactly this "shit": a curve-fit constant, not a sourced formula. Replaced with
-- MSCI's own real, published Momentum Tilt Index formula (MSCI Momentum Indexes Methodology,
-- August 2021, section 2.2.2): z-score winsorized at +/-3, then
-- Score = 1+Z (Z>0) or (1-Z)^-1 (Z<0), weight = market_cap * Score. No fitted constant. See
-- loaders/stock_scores/market_cap_tilt.py's module comment for the full citation.
--
-- One column per pillar (not just composite) because real ActiveBeta-style construction
-- tilts EACH factor sub-index independently by that factor's own z-score before combining -
-- matching that means the "Quality Leaders" tab should rank by quality's own tilted weight,
-- not composite's.

ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS composite_tilted_weight DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS momentum_tilted_weight DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS quality_tilted_weight DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS value_tilted_weight DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS growth_tilted_weight DOUBLE PRECISION;
ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS risk_tilted_weight DOUBLE PRECISION;

COMMENT ON COLUMN stock_scores.composite_tilted_weight IS
    'Display-only market-cap-tilted weight (market_cap * max(0.1, 1 + 0.2*composite_z)) for leaderboard/comparison ranking, matching real cap-weighted-parent + factor-tilt index construction (Goldman ActiveBeta). Computed once by a batch pass, NOT used by composite_score itself or any live trading logic - composite_score stays pure factor-merit. NULL until the batch pass first runs / for symbols missing market_cap.';
COMMENT ON COLUMN stock_scores.momentum_tilted_weight IS
    'Display-only market-cap-tilted weight for the Momentum pillar (same formula/rationale as composite_tilted_weight, tilted by momentum_score''s own z-score). Not used in any trading logic.';
COMMENT ON COLUMN stock_scores.quality_tilted_weight IS
    'Display-only market-cap-tilted weight for the Quality pillar (same formula/rationale as composite_tilted_weight, tilted by quality_score''s own z-score). Not used in any trading logic.';
COMMENT ON COLUMN stock_scores.value_tilted_weight IS
    'Display-only market-cap-tilted weight for the Value pillar (same formula/rationale as composite_tilted_weight, tilted by value_score''s own z-score). Not used in any trading logic.';
COMMENT ON COLUMN stock_scores.growth_tilted_weight IS
    'Display-only market-cap-tilted weight for the Growth pillar (same formula/rationale as composite_tilted_weight, tilted by growth_score''s own z-score). Not used in any trading logic.';
COMMENT ON COLUMN stock_scores.risk_tilted_weight IS
    'Display-only market-cap-tilted weight for the Risk/Safety pillar (same formula/rationale as composite_tilted_weight, tilted by risk_score''s own z-score). Not used in any trading logic.';
