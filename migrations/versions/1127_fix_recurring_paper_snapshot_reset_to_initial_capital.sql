-- Migration 1127: Repair algo_portfolio_snapshots rows corrupted by the SAME bug class as
-- migration 1112, recurring in a new form - plus rows migration 1112 itself missed.
--
-- migration 1112 only matched rows where total_portfolio_value was EXACTLY 100006.0. Live data
-- shows 2026-07-06 through 2026-07-12 stuck at 100001.97/99920.23/99927.56 (same fabricated-
-- near-$100k pattern, different trailing cents) - migration 1112's narrow exact-value guard
-- silently missed all of them despite its own comment stating this whole window's real,
-- broker-confirmed equity was flat at $72,029.10 ("no trading occurred"). This migration widens
-- the repair to the full 2026-07-06 through 2026-07-20 window using a tolerant guard instead of
-- an exact-value match.
--
-- ROOT CAUSE: DailyReconciliation.run_daily_reconciliation()'s `self.broker is None` LOCAL_MODE
-- fallback (algo/infrastructure/reconciliation.py) computed portfolio_value as an ABSOLUTE value:
--   initial_capital_paper_trading (config, $100,000) + SUM(profit_loss_dollars over ALL closed
--   algo_trades) + SUM(unrealized_pnl over currently-open algo_positions)
-- instead of rolling FORWARD from the previously recorded snapshot. This account's real,
-- broker-confirmed equity was $72,029.10 as of migration 1112 (verified against Alpaca's own
-- portfolio history) - a real ~28% loss that predates algo_trades-based tracking and is not
-- represented anywhere in that table's SUM(). Every time this fallback ran with zero open
-- positions and zero *known* (non-NULL) realized P&L in algo_trades - which is the common case,
-- since Alpaca credentials in this environment are placeholder test values ("PK012345...") that
-- can never authenticate, so the true broker equity can no longer be independently reconciled -
-- the formula collapsed back to the $100,000 config constant, erasing the real loss from the
-- equity curve exactly like migration 1112 describes. This flip-flopped algo_portfolio_snapshots
-- between ~$100,000 and $72,029.10 run to run throughout 2026-07-13 through 2026-07-20 depending
-- on which reconciliation happened to run last that day, repeatedly tripping (or masking) the
-- drawdown circuit breaker on unrelated runs.
--
-- No confirmed (non-NULL) realized P&L exists anywhere in algo_trades for this entire window
-- (verified live: the only trades closed in this period recorded NULL profit_loss_dollars,
-- correctly marked "pending broker fill reconciliation" since there is no reachable broker to
-- confirm a real fill price against) - so there is no evidence of any real equity change since
-- the last confirmed value. Restore the last broker-confirmed baseline for every row in this
-- window that shows the corrupted (reset-to-initial-capital) pattern, matching migration 1112's
-- own precedent of carrying forward the last confirmed real value when no real change is evidenced.
--
-- The recurrence itself is fixed in the same commit as this migration (see
-- algo/infrastructure/reconciliation.py): the LOCAL_MODE fallback now rolls forward from the prior
-- snapshot's total_portfolio_value instead of recomputing an absolute value from initial_capital,
-- so this specific corruption cannot happen again regardless of algo_trades' completeness.

UPDATE algo_portfolio_snapshots
SET total_portfolio_value = 72029.10,
    total_cash = 72029.10,
    total_equity = 72029.10,
    updated_at = CURRENT_TIMESTAMP
WHERE snapshot_date BETWEEN '2026-07-06' AND '2026-07-20'
  AND position_count = 0
  AND total_portfolio_value BETWEEN 90000 AND 105000;

-- Rows with open positions during the window still need total_portfolio_value/total_equity
-- restored to the confirmed baseline, but total_cash must stay internally consistent (cash =
-- portfolio_value - invested cost basis of open positions at that date), not simply overwritten
-- to 72029.10. Recompute it from each row's own invested amount (total_portfolio_value -
-- total_cash, as originally stored, is that day's invested capital, and is unaffected by which
-- of $100,000/$72,029.10 was used as the corrupted absolute baseline).
UPDATE algo_portfolio_snapshots
SET total_cash = 72029.10 - (total_portfolio_value - total_cash),
    total_portfolio_value = 72029.10,
    total_equity = 72029.10,
    updated_at = CURRENT_TIMESTAMP
WHERE snapshot_date BETWEEN '2026-07-06' AND '2026-07-20'
  AND position_count > 0
  AND total_portfolio_value BETWEEN 90000 AND 105000;

-- Recompute daily_return_pct for the day immediately following each repaired row so
-- circuit_breaker.py's Daily Loss Limit check (which reads this stored column directly) doesn't
-- see a stale return computed against the pre-repair value.
UPDATE algo_portfolio_snapshots s
SET daily_return_pct = 0.00,
    updated_at = CURRENT_TIMESTAMP
FROM (
    SELECT snapshot_date FROM algo_portfolio_snapshots
    WHERE snapshot_date BETWEEN '2026-07-06' AND '2026-07-20'
) repaired
WHERE s.snapshot_date = repaired.snapshot_date + INTERVAL '1 day'
  AND s.total_portfolio_value = 72029.10;
