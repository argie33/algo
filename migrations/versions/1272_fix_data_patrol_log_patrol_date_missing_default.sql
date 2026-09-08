-- Migration 1272: Fix data_patrol_log.patrol_date - live table had no DEFAULT despite
-- schema.sql declaring `patrol_date DATE DEFAULT CURRENT_DATE`.
--
-- Found during a goal-session score-sanity/tie-out sweep (2026-09-08): investigating why
-- `SELECT max(patrol_date) FROM data_patrol_log` returned 2026-07-05 while the table was
-- actively receiving fresh rows every few minutes (max(created_at) same-day). Root cause,
-- confirmed via `information_schema.columns.column_default` on the live table: it is NULL,
-- not `CURRENT_DATE` - a schema-drift bug (the column's default was either never applied at
-- table-creation time or was dropped at some point). None of PatrolLogger's three INSERT
-- statements (algo/monitoring/data_patrol/logger.py) list patrol_date in their column list,
-- relying entirely on the schema default to populate it - so every row inserted since
-- whatever event caused the drift has patrol_date left NULL. Confirmed live:
-- `SELECT count(*) FROM data_patrol_log WHERE patrol_date IS NULL` = 3,419 of 3,420 total
-- rows (only one stray July row happens to have a real value).
--
-- Not a production-safety bug: Phase 1's DataPatrol freshness gate
-- (algo/orchestrator/phase1_data_freshness.py's _check_data_patrol_results) queries
-- `created_at`, not `patrol_date`, so this never caused a false halt or a false pass. But
-- `idx_data_patrol_log_date` (lambda/db-init/schema.sql) is an index on a column that is
-- always NULL for practical purposes, and any operator or dashboard query filtering by
-- patrol_date (the column's own name strongly implies that's its intended use) silently
-- gets nothing for the entire recent history.
--
-- Restores the default going forward and backfills existing NULL rows from created_at's own
-- date - the closest available true patrol-run date for historical rows.

ALTER TABLE data_patrol_log ALTER COLUMN patrol_date SET DEFAULT CURRENT_DATE;

UPDATE data_patrol_log
SET patrol_date = created_at::date
WHERE patrol_date IS NULL;
