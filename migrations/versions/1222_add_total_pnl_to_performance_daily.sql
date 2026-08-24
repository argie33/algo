-- Migration 1222: Add total_pnl_dollars to algo_performance_daily
--
-- Found 2026-08-24 (real-money-readiness audit): lambda/api/routes/algo_handlers/metrics.py's
-- _get_algo_performance() returns total_pnl_dollars as unconditionally None, per its own
-- comment: "its source table has had no writer since 2026-06-30" (the old
-- algo_performance_metrics table). That table's replacement, algo_performance_daily
-- (written every orchestrator run by Phase 9 - algo/reporting/performance.py's
-- LivePerformance.generate_daily_report()), never had a total_pnl_dollars column at all -
-- so total lifetime P&L has been permanently unavailable in the dashboard, not just stale.
--
-- This is a genuine, easily-computable metric (SUM(profit_loss_dollars) over closed trades,
-- no complex derivation needed) that was simply never wired through. Adds the column here;
-- algo/reporting/performance.py computes and writes it, lambda/api/routes/algo_handlers/
-- metrics.py reads and returns the real value instead of a hardcoded None.

ALTER TABLE algo_performance_daily
    ADD COLUMN IF NOT EXISTS total_pnl_dollars NUMERIC(14, 2);
