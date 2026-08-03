-- Migration 1184: Add remaining untracked columns needed by GET /api/scores
--
-- ISSUE: same untracked-drift class as migrations 1181/1182/1183 - lambda/api/routes/
-- scores.py's stock-scores query, and the real loaders that feed it, both reference several
-- more columns with no versioned migration anywhere:
--
-- - annual_income_statement.gross_profit: fetched/mapped by
--   loaders/load_financial_statements.py (field_mapping "gross_profit" -> "gross_profit"),
--   read by lambda/api/routes/scores.py's gross-margin fallback.
-- - quality_metrics.quarterly_growth_momentum(+reason): migration 1174 added this column to
--   growth_metrics only, but scores.py reads it via the qm. (quality_metrics) alias -
--   adding the same column to quality_metrics rather than changing the query's alias, since
--   growth_metrics already has real data flowing into its own copy and this is the lower-risk
--   fix.
-- - positioning_metrics.shares_short_prior_month/short_interest_trend(+reasons),
--   insider_ownership_pct_unavailable_reason, short_interest_pct_unavailable_reason: written
--   by loaders/load_positioning_metrics.py, never migrated.
-- - stability_metrics.downside_volatility_30d/60d/252d(+reasons),
--   volatility_60d_unavailable_reason, volatility_252d_unavailable_reason: written by
--   loaders/load_risk_metrics_daily.py, never migrated (migration 1144's own name
--   "add_downside_volatility_metrics" suggests this was intended but the file doesn't
--   actually touch stability_metrics - a documentation/implementation mismatch, not
--   investigated further here since the fix is the same either way: add the columns).
-- - value_metrics.held_percent_insiders/held_percent_institutions: written by
--   loaders/load_value_quality_growth_metrics.py, never migrated.
--
-- Confirmed live: a local dev database missing any of these 503s GET /api/scores with the
-- corresponding UndefinedColumn error.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS gross_profit NUMERIC(20, 2);

ALTER TABLE quality_metrics
    ADD COLUMN IF NOT EXISTS quarterly_growth_momentum NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS quarterly_growth_momentum_unavailable_reason VARCHAR(255);

ALTER TABLE positioning_metrics
    ADD COLUMN IF NOT EXISTS shares_short_prior_month BIGINT,
    ADD COLUMN IF NOT EXISTS shares_short_prior_month_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS short_interest_trend VARCHAR(20),
    ADD COLUMN IF NOT EXISTS short_interest_trend_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS insider_ownership_pct_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS short_interest_pct_unavailable_reason VARCHAR(255);

ALTER TABLE stability_metrics
    ADD COLUMN IF NOT EXISTS downside_volatility_30d NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS downside_volatility_30d_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS downside_volatility_60d NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS downside_volatility_60d_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS downside_volatility_252d NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS downside_volatility_252d_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS volatility_60d_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS volatility_252d_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
    ADD COLUMN IF NOT EXISTS held_percent_insiders NUMERIC(6, 2),
    ADD COLUMN IF NOT EXISTS held_percent_institutions NUMERIC(6, 2);
