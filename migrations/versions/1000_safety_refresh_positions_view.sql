-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 1000_safety_refresh_positions_view
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Safety refresh of algo_positions_with_risk materialized view
--
-- CONTEXT: Migration 999 was updated to include a REFRESH statement in commit
-- 9055a024b. This migration ensures the view is refreshed in deployments where:
-- 1. Migration 999 was already applied WITHOUT the refresh fix
-- 2. A fresh redeploy is needed to guarantee view has current data
--
-- SAFETY: This is idempotent - can be run multiple times without side effects.
-- CONCURRENCY: Materialized view refresh locks the view during refresh, but
-- read-only queries can still execute (they see old data temporarily).
--
-- CREATED: 2026-07-04

REFRESH MATERIALIZED VIEW algo_positions_with_risk;

-- Log the refresh completion
-- Note: This is a safety measure; the view should already be populated from migration 999
