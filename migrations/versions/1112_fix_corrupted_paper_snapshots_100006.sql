-- Migration 1112: Repair fabricated algo_portfolio_snapshots rows (total_portfolio_value = 100006.0)
-- that falsely tripped the drawdown/daily_loss/weekly_loss circuit breakers and halted live paper
-- trading.
--
-- ROOT CAUSE (fixed in the same commit as this migration, see algo/infrastructure/reconciliation.py):
-- DailyReconciliation.run_daily_reconciliation()'s `self.broker is None` branch (intended only for
-- local dev without Alpaca credentials) computed a synthetic portfolio_value = initial_capital_paper_
-- trading (config default $100,000) + unrealized_pnl of open algo_positions, then WROTE it into
-- algo_portfolio_snapshots as if it were real broker-sourced equity. Because production credentials
-- were unavailable during some reconciliation runs between 2026-07-06 and 2026-07-12, this fabricated
-- ~$100,006 value was persisted for those 7 days, verified live against Alpaca's own portfolio history
-- (/v2/account/portfolio/history), which shows real equity flat at $72,029.10 (no trading occurred --
-- consistent with the Phase 1 halt bug blocking live trading that same week, see migration 1110).
--
-- IMPACT: circuit_breaker.py's _check_drawdown/_check_weekly_loss compute MAX(total_portfolio_value)
-- and 7-day-ago total_portfolio_value LIVE from this table (not from a stored aggregate), so the fake
-- $100,006 peak/baseline made 2026-07-13's real $72,029.10 equity look like a 27.98% drawdown/daily/
-- weekly loss -- tripping 3 of 9 circuit breakers and halting all new trade entries.
--
-- FIX: restore the real broker-confirmed total_portfolio_value/total_equity for the corrupted dates,
-- and recompute 2026-07-13's daily_return_pct (a stored column _check_daily_loss reads directly) against
-- the corrected 2026-07-12 baseline. 2026-07-06 has no exact broker record (Alpaca's history API skips
-- it); carried forward from 2026-07-03's confirmed real value since no trading activity occurred that
-- day. Guarded by the exact known-corrupted value so this is idempotent and a no-op if already applied.

UPDATE algo_portfolio_snapshots
SET total_portfolio_value = 72718.43,
    total_equity = 72718.43,
    updated_at = CURRENT_TIMESTAMP
WHERE snapshot_date = '2026-07-06'
  AND total_portfolio_value = 100006.0;

UPDATE algo_portfolio_snapshots
SET total_portfolio_value = 72029.10,
    total_equity = 72029.10,
    updated_at = CURRENT_TIMESTAMP
WHERE snapshot_date IN ('2026-07-07', '2026-07-08', '2026-07-09', '2026-07-10', '2026-07-11', '2026-07-12')
  AND total_portfolio_value = 100006.0;

UPDATE algo_portfolio_snapshots
SET daily_return_pct = 0.00,
    updated_at = CURRENT_TIMESTAMP
WHERE snapshot_date = '2026-07-13'
  AND daily_return_pct < -10.0;
