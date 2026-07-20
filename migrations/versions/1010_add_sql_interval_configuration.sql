-- Migration 1010: Add Configuration for SQL INTERVALS and RETRY COUNTS
-- Purpose: Add configuration keys for SQL query lookback periods and retry attempts
-- Replaces: 80+ hardcoded INTERVAL values in SQL queries + 3 hardcoded retry counts
-- Status: Replaces hardcoded values (medium effort optimization + low effort optimization)

-- Insert SQL interval configuration keys (replaces 80+ hardcoded INTERVAL values)
INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
VALUES
    ('sql_interval_1d_days', '1', 'int', '1-day lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_7d_days', '7', 'int', '7-day lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_14d_days', '14', 'int', '14-day lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_24h_days', '1.0', 'float', '24-hour lookback interval for SQL queries (in days)', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_30d_days', '30', 'int', '30-day lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_50d_days', '50', 'int', '50-day lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_60d_days', '60', 'int', '60-day lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_90d_days', '90', 'int', '90-day lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_365d_days', '365', 'int', '365-day (1-year) lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    ('sql_interval_52w_days', '364', 'int', '52-week (~364-day) lookback interval for SQL queries', CURRENT_TIMESTAMP, 'migration'),
    -- Retry configuration keys (replaces 3 hardcoded retry counts)
    ('retry_count_fred_api', '5', 'int', 'FRED API rate-limit retry attempts', CURRENT_TIMESTAMP, 'migration'),
    ('retry_count_aaii_sentiment', '2', 'int', 'AAII sentiment fetch retry attempts', CURRENT_TIMESTAMP, 'migration'),
    ('retry_count_db_migration', '3', 'int', 'Database migration blocking query cleanup retry attempts', CURRENT_TIMESTAMP, 'migration')
ON CONFLICT (key) DO NOTHING;
