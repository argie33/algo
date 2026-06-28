-- Migration 084: Set phase1_min_symbol_count to 5000
--
-- The code default was accidentally changed to 8000 in commit f33da2a94, but the
-- actual stock universe is ~5600 symbols (after ETF/warrant filtering). With 8000
-- as the threshold, Phase 1 halts on every orchestrator run, blocking all trading.
-- 5000 matches the steering doc and gives a ~600-symbol margin above the typical load.
--
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('phase1_min_symbol_count', '5000', 'int',
        'Min absolute symbol count in price_daily for Phase 1 to pass (actual universe ~5600)',
        'migration-084')
ON CONFLICT (key) DO UPDATE
    SET value = '5000',
        description = 'Min absolute symbol count in price_daily for Phase 1 to pass (actual universe ~5600)',
        updated_by = 'migration-084',
        updated_at = CURRENT_TIMESTAMP;
