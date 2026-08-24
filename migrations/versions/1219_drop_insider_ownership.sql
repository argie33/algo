-- Migration 1219: Drop insider_ownership_pct and insider_holdings_sec entirely
--
-- DECISION: insider_ownership_pct (% of shares outstanding held by insiders, from SEC
-- Form 3/4/5 bulk data via insider_holdings_sec) is removed entirely - it was scored as
-- 20% of the per-stock positioning_score (itself 15% of the composite score, ~3% of final
-- score). Conclusion: a static, slow-moving governance/alignment metric, not a real
-- positioning or sentiment signal, and this system trades a weeks-scale swing/breakout
-- timeframe where a near-time-invariant per-symbol metric has near-zero information
-- content. Also a recurring source of real bugs (foreign-private-issuer exemption
-- handling, shares-outstanding edge cases). See loaders/DEPRECATED_LOADERS.md.
--
-- Does NOT touch insider_transactions or insider_transaction_velocity - those back a
-- separate, real, dynamic signal (net insider buy/sell dollar value, trailing 60 days;
-- algo/signals/advanced_filters.py's CATALYST _insider_score()) and are unrelated.
--
-- insider_holdings_sec: created by migration 1019 (symbol, filing_date) PK, later
-- collapsed to a symbol-only PK by migration 1124 (dedup + snapshot-style upsert) and
-- referenced (not altered) by 1125's comment. No FK from any other table points at it
-- (confirmed via information_schema / grep) - migration 1146's insider_transactions
-- table was never actually created FROM this table (that DDL block never ran, see that
-- migration's own docstring), so DROP TABLE is safe with no cascade needed elsewhere.
--
-- positioning_metrics.insider_ownership_pct: renamed from insider_ownership by migration
-- 1023. insider_ownership_pct_unavailable_reason: added (redundantly, both IF NOT EXISTS)
-- by migrations 1145 and 1184 - single real column, exact name confirmed by reading both
-- before writing this migration.

DROP TABLE IF EXISTS insider_holdings_sec;

ALTER TABLE positioning_metrics
    DROP COLUMN IF EXISTS insider_ownership_pct,
    DROP COLUMN IF EXISTS insider_ownership_pct_unavailable_reason;

-- value_metrics.held_percent_insiders/held_percent_insiders_unavailable_reason
-- (migrations 1184 and 104 respectively) copied positioning_metrics.insider_ownership_pct
-- for display via loaders/load_value_quality_growth_metrics.py's _fetch_positioning_metrics
-- - dropped along with its source column. held_percent_institutions/
-- held_percent_institutions_unavailable_reason are untouched.
ALTER TABLE value_metrics
    DROP COLUMN IF EXISTS held_percent_insiders,
    DROP COLUMN IF EXISTS held_percent_insiders_unavailable_reason;
