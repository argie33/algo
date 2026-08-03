-- Migration 1179: Add analyst_earnings_estimates table (real forward EPS for forward_pe)
--
-- ISSUE: value_metrics.forward_pe has been permanently unavailable for 99.8% of symbols
-- (5477/5486 carry "analyst_estimates_not_in_sec_filings") because forward_pe was hardcoded
-- None in load_sec_valuations.py - correctly, since SEC filings never carry forward-looking
-- EPS estimates (that's inherently third-party analyst data).
--
-- FIX: same "unofficial but real, transparently documented" tradeoff already accepted for
-- analyst_upgrade_downgrade/analyst_sentiment_analysis (see
-- utils/external/yfinance_analyst_ratings.py's docstring) - yf.Ticker.earnings_estimate is a
-- real, free, non-.info API surface giving consensus next-FY EPS estimates. New standalone
-- snapshot table (own loader, own yfinance-circuit-breaker cadence, matching the existing
-- analyst_sentiment_analysis architecture) - load_value_quality_growth_metrics.py joins this
-- to compute value_metrics.forward_pe = current_price / forward_eps.

CREATE TABLE IF NOT EXISTS analyst_earnings_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    forward_eps NUMERIC(12, 4),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(100),
    data_source VARCHAR(50) DEFAULT 'yfinance_earnings_estimate',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_analyst_earnings_estimates_symbol ON analyst_earnings_estimates(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_earnings_estimates_date ON analyst_earnings_estimates(date DESC);

COMMENT ON TABLE analyst_earnings_estimates IS
    'Consensus next-fiscal-year EPS estimate per symbol from yfinance Ticker.earnings_estimate (real analyst consensus, not an SEC concept - forward estimates are inherently third-party). Feeds value_metrics.forward_pe.';
