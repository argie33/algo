-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION 048: Remove legacy positions table
-- ════════════════════════════════════════════════════════════════════════════
--
-- ISSUE #5: Conflicting Table Names
--
-- BACKGROUND:
-- The system historically had a `positions` table that was replaced by
-- `algo_positions` in Phase 3. The old table is now:
-- - Empty (0 rows)
-- - Unused (no code references it, no foreign keys)
-- - Confusing (2 similar table names cause architectural clarity issues)
--
-- SOURCE OF TRUTH:
-- `algo_positions` is the ONLY positions data source:
-- - Stores active trading positions (12 rows currently)
-- - Used by `algo_positions_with_risk` view (enriches with stops/targets/risk)
-- - Dashboard queries the view, not the raw table
--
-- ACTION:
-- Drop the legacy `positions` table to eliminate confusion.
-- All position data now flows through `algo_positions` → `algo_positions_with_risk` view.

DROP TABLE IF EXISTS positions CASCADE;

-- Verify the change by ensuring only algo_positions and manual_positions remain
-- (no bare `positions` table)
