-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 1000_refresh_positions_view_after_creation
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Ensure algo_positions_with_risk materialized view is populated
--
-- ISSUE: Migration 999 created the materialized view but didn't refresh it.
-- If 999 was deployed before the refresh statement was added, the view is empty.
-- This migration refreshes the view to populate it with position data.
--
-- This is a safety measure: if 999 already had the refresh, this is idempotent.
-- If 999 didn't have the refresh, this fixes the empty view.
--
-- CREATED: 2026-07-04

-- Refresh the materialized view to populate it with position data
-- This is safe to run multiple times (idempotent)
REFRESH MATERIALIZED VIEW algo_positions_with_risk;

-- Log successful refresh
DO $$
BEGIN
  RAISE NOTICE 'Successfully refreshed algo_positions_with_risk materialized view';
END $$;

COMMENT ON MATERIALIZED VIEW algo_positions_with_risk IS
'CRITICAL: Enriched positions with stops, targets, sector, technical scores, and risk metrics. Single source of truth for dashboard. Refreshed by migration 1000 (2026-07-04).';
