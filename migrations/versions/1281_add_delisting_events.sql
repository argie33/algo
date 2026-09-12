-- Migration 1281: Add delisting_events - captures the moment a symbol is genuinely
-- delisted/removed from the exchange feed, going forward.
--
-- Goal session 2026-09-12 ("figure out the right methodology, address it all"): the
-- survivorship-bias audit this session found (see MEMORY.md
-- survivorship_bias_concretely_reverified_zero_rows_named_failures_20260912) that this repo
-- has ZERO tracking of when/why a symbol disappears - `stock_symbols.active=false` with a
-- free-text `data_unavailable_reason` is the only record, and for the 44 symbols genuinely
-- flagged 'delisted_or_removed_from_exchange_feed' (loaders/load_market_constituents.py's
-- `_deactivate_symbols_delisted_from_exchange_feed`), even that string carries no date, no
-- last-known price, and doesn't distinguish bankruptcy from a benign acquisition. Checked
-- whether the free academic alternative to buying delisting-return data (Shumway 1997/1999's
-- -30%/-55% imputation convention for missing performance-related delisting returns) could be
-- applied here instead of a paid vendor - it can't, because that technique needs a delisting
-- EVENT LOG (date + reason) which this schema never captured at all, even for symbols this
-- system's own loaders already know went away.
--
-- This does NOT fix the historical 2000-2026 gap (Lehman/Enron/etc. were never in this
-- database to begin with, long before this table existed) - only a real data vendor backfill
-- closes that. This closes the narrower, ongoing gap: from today forward, a symbol that
-- exits the tracked universe for a detected reason gets an actual record (last price, last
-- price date, detection reason) instead of silently vanishing with no trace, so this exact
-- blind spot does not keep recurring for every future real-world company failure.

CREATE TABLE IF NOT EXISTS delisting_events (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    detection_reason VARCHAR(100) NOT NULL,
    last_price_date DATE,
    last_price NUMERIC,
    UNIQUE (symbol, detection_reason)
);
CREATE INDEX IF NOT EXISTS idx_delisting_events_symbol ON delisting_events(symbol);
