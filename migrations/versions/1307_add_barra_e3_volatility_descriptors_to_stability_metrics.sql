-- Migration 1307: Add AQR Betting-Against-Beta (BAB) shrinkage beta columns to stability_metrics
--
-- SUPERSEDES this file's own original 2026-09-17 content, which added Barra US-E3 Volatility
-- descriptor columns (dastd_65d, cmra_12m) - see risk_scoring.py's module docstring for the
-- 2026-09-17 factor-purity pivot away from Barra-sourced risk descriptors toward AQR's real,
-- published low-beta anomaly construction (user directive: move Risk scoring to AQR, not a
-- Barra homegrown replica). dastd_65d was a dead column even under the original migration -
-- nothing in loaders/load_risk_metrics_daily.py ever wrote it (confirmed via grep before this
-- rewrite) - so it is dropped entirely rather than carried forward unused. cmra_12m stays (it
-- IS a correctly-implemented real Barra US-E3 descriptor, verified against the actual handbook
-- text - see _calculate_cmra's own docstring) but only as an informational, computed-not-scored
-- column, the same "compute it, don't score it" treatment this table already gives
-- amihud_illiquidity_60d after it failed this repo's own Fama-MacBeth/FDR bar.
--
-- BETA_BAB: Frazzini & Pedersen (2014, "Betting Against Beta", Journal of Financial Economics
-- 111(1)) shrinkage beta estimator - beta_ts = rho * (sigma_stock / sigma_market), where sigma
-- is each series' own 1-year daily-return volatility and rho is the correlation of 5-year
-- overlapping 3-day log returns; beta_bab = 0.6*beta_ts + 0.4*1.0 (the paper's own published
-- shrinkage weight w=0.6 and cross-sectional shrinkage target beta_XS=1, fixed constants, not
-- fitted to this repo's data). See loaders/load_risk_metrics_daily.py's `_calculate_beta_bab`
-- for the full citation and formula. beta_bab_ts/beta_bab_rho/beta_bab_sigma_ratio are the
-- estimator's own intermediate components, persisted for auditability (same "keep the intermediate
-- math, not just the final number" pattern this table already follows for cmra_12m's Z-values
-- being re-derivable from monthly inputs). The existing `beta` column (naive OLS, 1-year daily
-- returns vs SPY) is UNCHANGED and NOT overwritten - existing tests, dashboard, and coverage
-- reports read it; beta_bab is additive, not a replacement of that column.

BEGIN;

ALTER TABLE stability_metrics
ADD COLUMN IF NOT EXISTS cmra_12m NUMERIC(12, 8) NULL,
ADD COLUMN IF NOT EXISTS cmra_12m_unavailable_reason VARCHAR(255) NULL,
ADD COLUMN IF NOT EXISTS beta_bab NUMERIC(10, 4) NULL,
ADD COLUMN IF NOT EXISTS beta_bab_ts NUMERIC(10, 4) NULL,
ADD COLUMN IF NOT EXISTS beta_bab_rho NUMERIC(10, 6) NULL,
ADD COLUMN IF NOT EXISTS beta_bab_sigma_ratio NUMERIC(12, 6) NULL,
ADD COLUMN IF NOT EXISTS beta_bab_unavailable_reason VARCHAR(255) NULL;

COMMIT;
