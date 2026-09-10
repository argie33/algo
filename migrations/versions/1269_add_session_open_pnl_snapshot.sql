-- Migration 1269: Add a genuinely immutable per-day "session open" P&L snapshot
-- Date: 2026-09-07 (real-money-readiness audit)
--
-- ROOT CAUSE: algo/risk/unified_risk_monitor.py's _check_portfolio_variance (and the
-- legacy lambda/circuit-breaker/index.py::get_portfolio_pnl it was ported from - same bug,
-- not yet fixed there) computes intraday portfolio variance as
-- (current live P&L - "session open" P&L) / equity, reading the "session open" value from
-- algo_portfolio_snapshots.unrealized_pnl_total WHERE snapshot_date = CURRENT_DATE.
--
-- That column is NOT a fixed once-a-day value: Phase 9 reconciliation always_run=True and
-- the production schedule runs the orchestrator (and therefore Phase 9) multiple times per
-- trading day - premarket 4:30am, morning 9:30am, afternoon 1:00pm, preclose 3:00pm, plus
-- an evening run (see terraform/modules/services/2x-daily-orchestrator.tf). Every one of
-- those Phase 9 runs UPSERTs the same snapshot_date row via
-- `INSERT ... ON CONFLICT (snapshot_date) DO UPDATE SET unrealized_pnl_total = EXCLUDED...`
-- (reconciliation_broker_snapshot.py / reconciliation_paper_mode.py), overwriting
-- unrealized_pnl_total with whatever the CURRENT value is at that run - not preserving the
-- actual 9:30am market-open value.
--
-- Concrete failure mode: a portfolio that draws down 10% between 9:30am and 1:00pm would
-- (correctly) show ~-10% variance and could trip the auto-halt/reduce ladder. But the
-- 1:00pm orchestrator run's Phase 9 execution then overwrites unrealized_pnl_total to the
-- ALREADY-DEPRESSED 1:00pm value - silently resetting the "open_pnl" baseline every
-- unified_risk_monitor check reads. If the portfolio then slides ANOTHER 8% by 3:00pm, the
-- variance check measures only -8% against the reset 1pm baseline, not the true -18% since
-- actual session open - potentially staying under threshold and failing to halt/reduce a
-- real, sustained, cumulative intraday loss. This is the exact failure mode a real-money
-- intraday circuit breaker exists to catch.
--
-- FIX: a new column, written ONCE per trading day at first-insert and never touched by any
-- later ON CONFLICT UPDATE for that snapshot_date (see reconciliation_broker_snapshot.py /
-- reconciliation_paper_mode.py's matching change) - genuinely represents the first Phase 9
-- write of the day (premarket/morning, effectively at-or-before market open), immune to
-- being overwritten by subsequent same-day runs. unified_risk_monitor.py's
-- _check_portfolio_variance is updated to read this column instead.

BEGIN;

ALTER TABLE algo_portfolio_snapshots
    ADD COLUMN IF NOT EXISTS session_open_unrealized_pnl_total NUMERIC(18, 2);

COMMENT ON COLUMN algo_portfolio_snapshots.session_open_unrealized_pnl_total IS
    'unrealized_pnl_total as of the FIRST Phase 9 reconciliation write for this snapshot_date (effectively market-open) - set once on INSERT and deliberately excluded from every ON CONFLICT DO UPDATE clause so later same-day Phase 9 runs cannot overwrite it. unrealized_pnl_total itself keeps updating live as the current-state column; this column is the fixed intraday-variance baseline. See migration 1269 for the bug this closes.';

-- One-time backfill: for existing rows, the current unrealized_pnl_total is the best
-- available approximation (no historical intraday timeseries exists to recover the true
-- first-write value) - going forward, new rows get the real first-write value.
UPDATE algo_portfolio_snapshots
SET session_open_unrealized_pnl_total = unrealized_pnl_total
WHERE session_open_unrealized_pnl_total IS NULL;

COMMIT;
