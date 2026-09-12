-- Migration 1280: Add score_realized_ic_log - the missing live feedback loop for stock_scores.
--
-- Goal session 2026-09-12 ("question everything about our scoring methodology"): audited what
-- institutional multi-factor shops do that this repo didn't - alongside survivorship bias and
-- multiple-comparisons correction (both already addressed this session), the third structural
-- gap found was that NOTHING tracks whether the live composite/pillar scores actually predict
-- forward returns once they're in production. Every existing check (fama_macbeth_*.py,
-- backtest scripts) is a one-off OFFLINE test against historical data - there was no ongoing,
-- accumulating record of realized Information Coefficient (rank correlation between a score
-- as of a date and that symbol's subsequent actual return) to catch decay or a bad assumption
-- in the real, live-scored universe.
--
-- stock_scores_history (daily snapshot, started 2026-08-24) already exists and already has the
-- raw material for this - it was just never queried for it. This table stores the computed IC
-- time series so it accumulates and can be trended/alerted on, the same
-- accumulates-over-many-runs posture as xbrl_yfinance_crosscheck.py's rotating sample.

CREATE TABLE IF NOT EXISTS score_realized_ic_log (
    id BIGSERIAL PRIMARY KEY,
    score_date DATE NOT NULL,
    horizon_trading_days INTEGER NOT NULL,
    score_name VARCHAR(30) NOT NULL,
    ic NUMERIC,
    n_symbols INTEGER NOT NULL,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (score_date, horizon_trading_days, score_name)
);
CREATE INDEX IF NOT EXISTS idx_score_realized_ic_log_name_date
    ON score_realized_ic_log(score_name, score_date);
