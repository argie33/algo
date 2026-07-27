-- Migration 1163: Add last-success timestamp and consecutive-failure tracking to
-- data_loader_status.
--
-- Gap: data_loader_status.execution_completed is stamped on EVERY terminal outcome
-- (mark_completed, mark_failed, and mark_timeout in utils/loaders/status_manager.py all
-- set it), so it cannot distinguish "last time this loader finished successfully" from
-- "last time it finished at all (including a failure)". Likewise there was no way to
-- tell "failed once, transient" from "failed every run for a week" without reading raw
-- logs - a loader stuck FAILED for 5 consecutive days and one that just failed once
-- both looked identical on the dashboard.
--
-- Both columns are nullable/defaulted and populated going forward only (no backfill -
-- there is no reliable historical signal to reconstruct consecutive_failures or
-- last_success_at from existing rows, since execution_completed already conflates
-- success/failure). Safe to add on a live table: no lock beyond the DDL itself, no
-- rewrite of existing rows required for nullable ADD COLUMN in Postgres.

ALTER TABLE data_loader_status
    ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0;
