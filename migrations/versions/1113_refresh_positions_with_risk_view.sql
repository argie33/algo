-- Migration 1113: Force-refresh algo_positions_with_risk materialized view
--
-- ISSUE: /api/algo/positions returns 0 rows live ("[POSITIONS CRITICAL] algo_positions_with_risk
-- returned 0 rows") while algo_portfolio_snapshots.position_count reports 3 open positions for
-- the same moment. algo_positions_with_risk (migration 1103) is a MATERIALIZED view, only
-- refreshed by Phase 9 reconciliation after a successful orchestrator run -- it does not
-- auto-update when algo_positions changes. Phase 9 has not completed successfully in days
-- (blocked by the Phase 1 config halt, then missing broker credentials, then the price-loader
-- lock-table bug -- all fixed earlier today), so this view is stale relative to algo_positions.
--
-- FIX: refresh it directly so the dashboard positions panel reflects current data now, instead
-- of waiting for the next full orchestrator cycle to reach Phase 9.

REFRESH MATERIALIZED VIEW algo_positions_with_risk;
