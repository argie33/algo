-- Migration: Drop unused economic_metrics_daily table
--
-- Problem: economic_metrics_daily table exists but:
--   - Has no loader (identified in DATA_LOADERS.md as gap #2)
--   - Has no consumer code (verified 2026-07-25)
--   - Contains only 2 stale rows
--
-- Solution: Remove the table and all config references to it
--
-- Related: removed references from:
--   - lambda/api/routes/algo_handlers/market.py (health exclusion list)
--   - utils/data_tiers.py (auxiliary loaders list)
--   - utils/db/sql_safety.py (query whitelist)
--   - utils/loader_priority.py (priority config)

DROP TABLE IF EXISTS economic_metrics_daily CASCADE;
