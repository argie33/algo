-- Migration 1142: Add macd and macd_signal to buy_sell_daily
-- Date: 2026-07-20
--
-- ROOT CAUSE: algo/signals/buy_signal_generator.py computes "macd"/"macd_signal" for every
-- signal (lines 173-174) and includes them in the signal dict written to buy_sell_daily, but
-- no such columns existed on the table - bulk_insert_manager's generic schema-introspection
-- write path silently dropped both fields on every insert (WARNING log only, same bug class
-- as migrations 1139/1140/1141). webapp/frontend's signalTableHelpers.js already has dead
-- formatting rules for "macd"/"signal_line" waiting for data that never arrived.

BEGIN;

ALTER TABLE buy_sell_daily ADD COLUMN IF NOT EXISTS macd NUMERIC(12, 4);
ALTER TABLE buy_sell_daily ADD COLUMN IF NOT EXISTS macd_signal NUMERIC(12, 4);

COMMENT ON COLUMN buy_sell_daily.macd IS
    'MACD line value at signal generation time, computed by buy_signal_generator.py. Column was missing entirely before migration 1142; the value was computed but silently dropped by bulk_insert_manager schema filtering.';

COMMENT ON COLUMN buy_sell_daily.macd_signal IS
    'MACD signal line value at signal generation time, computed by buy_signal_generator.py. Column was missing entirely before migration 1142; the value was computed but silently dropped by bulk_insert_manager schema filtering.';

COMMIT;
