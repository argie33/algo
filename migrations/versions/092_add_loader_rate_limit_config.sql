-- Migration 092: Add loader rate limit configuration keys to algo_config
--
-- These keys were added to algo/infrastructure/config/main.py but never
-- migrated to the database, causing load_prices.py and other loaders to
-- fail with RuntimeError: Missing required configuration key.
--
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('loader_rate_limit_circuit_break_threshold_morning', '480', 'int',
        'Circuit break threshold (seconds) during morning prep (8 min)',
        'migration-092')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('loader_rate_limit_circuit_break_threshold_eod', '180', 'int',
        'Circuit break threshold (seconds) during EOD (3 min)',
        'migration-092')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('loader_rate_limit_requests_per_min', '120', 'int',
        'Rate limit: maximum requests per minute',
        'migration-092')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('loader_timeout_seconds', '300', 'int',
        'Loader operation timeout in seconds',
        'migration-092')
ON CONFLICT (key) DO NOTHING;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('loader_emergency_mode_threshold_multiplier', '0.5', 'float',
        'Emergency mode triggered at N% of task timeout',
        'migration-092')
ON CONFLICT (key) DO NOTHING;
