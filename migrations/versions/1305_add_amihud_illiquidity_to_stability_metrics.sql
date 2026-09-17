-- Migration 1305: Add Amihud (2002) illiquidity measure to stability_metrics
--
-- Amihud, Y. (2002), "Illiquidity and stock returns: cross-section and time-series effects",
-- Journal of Financial Markets - mean(|daily return| / dollar volume) over a trailing window,
-- one of the most replicated liquidity-premium measures in empirical finance. Flagged as an
-- OPEN QUESTION in loaders/stock_scores/risk_scoring.py's own module docstring (2026-08-25):
-- live-tested against this repo's own price_daily data (126 months, t=3.34, positive - more
-- illiquid genuinely predicts higher forward return here, matching the literature) but never
-- implemented because it needs a genuine new computation (no existing metrics table stores
-- daily |return|/dollar-volume), unlike Size which only needed reading an already-stored field.

BEGIN;

ALTER TABLE stability_metrics
ADD COLUMN IF NOT EXISTS amihud_illiquidity_60d NUMERIC(16, 10) NULL,
ADD COLUMN IF NOT EXISTS amihud_illiquidity_60d_unavailable_reason VARCHAR(255) NULL;

COMMIT;
