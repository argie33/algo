-- Migration 111: Add yfinance market close timeout configuration keys
-- load_prices.py requires these keys to be present in algo_config.
-- Without them, the loader crashes with RuntimeError when trying to determine
-- how long to wait for market close data to become available from yfinance API.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
    ('yfinance_market_close_timeout_eod_sec', '1800', 'int',
     'Timeout (seconds) waiting for market close data during EOD pipeline (4:05 PM ET, 30 min total deadline)',
     'migration-111'),
    ('yfinance_market_close_timeout_morning_sec', '600', 'int',
     'Timeout (seconds) waiting for market close data during morning pipeline (3:30-9:30 AM ET, generous buffer)',
     'migration-111')
ON CONFLICT (key) DO NOTHING;
