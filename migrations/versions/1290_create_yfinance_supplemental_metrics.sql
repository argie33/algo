-- Migration 1290: Create yfinance_supplemental_metrics.
--
-- Adds held_percent_insiders (% of shares held by insiders - distinct from
-- insider_transaction_velocity's buy/sell transaction-flow data, which is Form 3/4/5
-- activity, not a static ownership percentage). Confirmed this session to have no
-- equivalent anywhere in the schema and no SEC-XBRL-derivable source (not a standard
-- us-gaap/dei concept - Yahoo computes it from proprietary share-registry data).
--
-- SCOPE NOTE: 3 sibling fields originally considered (implied_shares_outstanding,
-- float_shares, five_year_avg_dividend_yield) are deliberately NOT included. All 3 only
-- exist via yfinance's `.info`/quoteSummary endpoint, which was deliberately removed from
-- this codebase 2026-07-21 (see steering/DATA_LOADERS.md "FIXED 2026-07-21: dead yfinance
-- quoteSummary (.info) code path removed") after real production incidents: 401-prone
-- "Invalid Crumb" failures and risk of tripping the SHARED cross-ECS-task yfinance circuit
-- breaker that the real OHLCV fallback path (utils/data/source_router.py) depends on. Every
-- yfinance-sourced loader added since that fix (analyst_sentiment_analysis, analyst_upgrade_
-- downgrade, analyst_earnings_estimates) deliberately uses non-.info DataFrame endpoints
-- (.upgrades_downgrades, .recommendations_summary, .earnings_estimate) instead - this table
-- follows that same convention. held_percent_insiders is safe because
-- yf.Ticker(symbol).major_holders is a separate, non-.info DataFrame property endpoint
-- (live-verified 2026-09-14: returns insidersPercentHeld/institutionsPercentHeld/
-- institutionsFloatPercentHeld/institutionsCount as a real DataFrame, no quoteSummary call).
-- The other 3 fields remain a real, known, currently-unclosable gap pending either a safe
-- non-.info source or a deliberate decision to accept .info's fragility for them specifically.
--
-- Deliberately a SEPARATE table, not a new column on value_metrics/positioning_metrics:
-- load_positioning_metrics.py and load_insider_transaction_velocity.py both carry an
-- explicit "no yfinance fallback, SEC-only" governance rule for their own tables since they
-- feed stock_scores directly. This data has no SEC source to fall back FROM - it's
-- yfinance-only by necessity - so it gets its own clearly-labeled table (data_source is
-- always 'yfinance', never silently blended into an SEC-sourced table) rather than
-- compromising an existing table's sourcing guarantee. Same precedent as sec_valuations.py's
-- data_source="sec_audited_except_dual_class_shares_yfinance" pattern: yfinance usage stays
-- explicit and auditable, never silent.
CREATE TABLE IF NOT EXISTS yfinance_supplemental_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    held_percent_insiders NUMERIC(9, 4),
    held_percent_insiders_unavailable_reason VARCHAR(100),
    data_source VARCHAR(20) NOT NULL DEFAULT 'yfinance',
    data_unavailable BOOLEAN NOT NULL DEFAULT FALSE,
    reason VARCHAR(200),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_yfinance_supplemental_metrics_updated_at
    ON yfinance_supplemental_metrics(updated_at);
