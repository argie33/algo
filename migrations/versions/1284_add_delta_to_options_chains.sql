-- Migration 1284: Create options_chains (it never existed) and add delta.
--
-- Same phantom-migration bug class as 1283's iv_history fix, found auditing this same
-- session's options work: options_chains has NEVER had a CREATE TABLE anywhere in this
-- repo's history. Migration 091 (2026-06-20) only ever ran `ALTER TABLE IF EXISTS
-- options_chains ...` against it - a silent no-op against a table that was never created,
-- exactly like iv_history's bug. loaders/load_options_chains.py (the loader migration 091
-- shipped alongside) was deleted 2026-07-11, a month later, as "unfinished", without this
-- ever being noticed. Without this CREATE TABLE, scripts/options_data_loader.py's INSERTs,
-- lambda/api/routes/options.py's SELECT, and algo/signals/signal_options.py's put/call-ratio
-- and implied-move signals all silently fail/return data_unavailable against a fresh or
-- local dev database - this migration is what actually makes the table exist for the first
-- time, matching every column those call sites already assume: the base set migration 091
-- expected (symbol, quote_date, iv, days_to_expiration) plus the fuller quote capture this
-- session's loader added (contract_symbol/option_type/strike_price/expiration_date/bid/ask/
-- last_price/volume/open_interest) and delta (self-computed via Black-Scholes from vendor
-- IV - utils/options/black_scholes.py - live-validated against MSFT that session; stored
-- alongside the quote it was computed from rather than recomputed on read, since it also
-- depends on the risk-free rate and time-to-expiry at capture time).
CREATE TABLE IF NOT EXISTS options_chains (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    contract_symbol VARCHAR(64),
    option_type VARCHAR(4) NOT NULL CHECK (option_type IN ('call', 'put')),
    strike_price DECIMAL(12, 4) NOT NULL,
    expiration_date DATE NOT NULL,
    bid DECIMAL(12, 4),
    ask DECIMAL(12, 4),
    last_price DECIMAL(12, 4),
    volume BIGINT,
    open_interest BIGINT,
    quote_date DATE NOT NULL,
    iv DECIMAL(8, 4),
    days_to_expiration DECIMAL(8, 2),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_options_chains_symbol_quote_date
    ON options_chains(symbol, quote_date DESC);

ALTER TABLE IF EXISTS options_chains
    ADD COLUMN IF NOT EXISTS delta DECIMAL(6, 4);
