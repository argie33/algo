-- Migration 1235: Rename stock_scores(_history).stability_score to risk_score
--
-- Pure rename, no computation change: the pillar's four inputs (60d volatility 45%,
-- beta 20%, 60d downside deviation 15%, 1y max drawdown 20%) are unchanged. This is the
-- "Stability" pillar renamed to "Risk" per user directive 2026-08-26 - see
-- loaders/load_stock_scores.py's _score_risk (formerly _score_stability) docstring.
--
-- Deliberately NOT renamed: the upstream stability_metrics input table and its loader
-- (loaders/load_risk_metrics_daily.py's _persist_stability_metrics/_get_stability_metrics) -
-- that's storage plumbing, not the user-facing factor name, and a much larger migration
-- than this rename warrants.
--
-- ALTER TABLE ... RENAME COLUMN is a metadata-only operation in Postgres - no table rewrite,
-- safe on a live table.

ALTER TABLE stock_scores RENAME COLUMN stability_score TO risk_score;
ALTER TABLE stock_scores_history RENAME COLUMN stability_score TO risk_score;
