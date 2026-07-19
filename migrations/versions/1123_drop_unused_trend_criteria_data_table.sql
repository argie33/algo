-- Migration 1123: Drop unused trend_criteria_data table
--
-- This table was identified as completely unused in the codebase (Session 255 audit).
-- Zero references across all Python code, loaders, orchestrator phases, or API endpoints.
-- Safe to delete with no impact on system functionality.
--
-- Affected: Dashboard, reporting, data patrol configs will not reference this table

BEGIN;

DROP TABLE IF EXISTS trend_criteria_data CASCADE;

COMMIT;
