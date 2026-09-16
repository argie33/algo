-- Migration 1300: Full line-item-level SEC-vs-yfinance cross-check persistence.
--
-- 2026-09-16 /goal session ("load all SEC data, validate every line item vs yahoo, measure
-- and report so we know the exact place any data issue still is"): scripts/
-- xbrl_yfinance_crosscheck.py previously only persisted flagged/divergent examples, capped at
-- 15 per field, as a JSONB blob inside data_patrol_log - fine for a WARN-review-queue posture,
-- useless for "show me the full matrix of every symbol x every line item we've compared." This
-- table stores every comparison (match or divergence) as its own row, upserted per (symbol,
-- our_table, our_field, fiscal_year), so repeated runs accumulate a durable, queryable record
-- instead of overwriting/discarding prior coverage. See scripts/xbrl_line_item_report.py for
-- the read side.
--
-- xbrl_yfinance_crosscheck_progress is a one-row cursor letting the crosscheck script sweep
-- the full active universe alphabetically across many rate-limit-safe runs (same "accumulate
-- over many small runs" posture as tiingo_backfill_status) instead of re-sampling a random 25
-- symbols forever, which never guarantees full coverage.

CREATE TABLE IF NOT EXISTS xbrl_yfinance_line_item_report (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    our_table VARCHAR(50) NOT NULL,
    our_field VARCHAR(80) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    our_value NUMERIC,
    yfinance_value NUMERIC,
    ratio NUMERIC,
    divergent BOOLEAN NOT NULL,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, our_table, our_field, fiscal_year)
);
CREATE INDEX IF NOT EXISTS idx_xbrl_yf_line_item_divergent
    ON xbrl_yfinance_line_item_report(our_table, our_field) WHERE divergent;
CREATE INDEX IF NOT EXISTS idx_xbrl_yf_line_item_symbol
    ON xbrl_yfinance_line_item_report(symbol);

CREATE TABLE IF NOT EXISTS xbrl_yfinance_crosscheck_progress (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_symbol VARCHAR(20),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
