-- Migration 1128: Remove/repair the two earliest algo_portfolio_snapshots rows, which are
-- fabricated seed/fixture data, not real trading history - and were silently anchoring the
-- circuit breaker's drawdown peak calculation to a fake number.
--
-- EVIDENCE these two rows (2026-06-29, 2026-06-30 - literally MIN(snapshot_date) on this table)
-- are not real: both share the IDENTICAL cumulative_return_pct = -20.0000% despite DIFFERENT
-- total_portfolio_value ($85,000 vs $80,000 - mathematically inconsistent as a -20% return off
-- the same $100k baseline), and both were inserted at the exact same timestamp
-- (2026-07-05 18:15:28), i.e. a single bulk backfill/seed operation, not organic day-by-day
-- reconciliation. Verified against Alpaca's own /v2/account/portfolio/history (authoritative,
-- same source migration 1112 used): this account (PA3KLJ0Y1HOP, created 2024-04-26) has no
-- record for 2026-06-29 at all, and 2026-06-30's real equity was $73,060.87 - nothing close to
-- either fake value.
--
-- IMPACT: circuit_breaker.py's _check_drawdown() computes peak = MAX(total_portfolio_value)
-- over this entire table. With every other row now correctly showing the real, broker-confirmed
-- $72,029.10 (2026-07-06 onward, restored by migration 1127), this fake $85,000 seed row became
-- the table's highest value and thus THE peak the live drawdown % is measured against -
-- understating the real drawdown (reported 15.26% instead of a value based on genuine history).
--
-- FIX: delete the unverifiable 2026-06-29 row (no real Alpaca record exists for that date -
-- fabricating a specific number here would just be a different flavor of the same problem this
-- migration is fixing), and correct 2026-06-30 to Alpaca's real confirmed equity ($73,060.87).
--
-- NOTE (not fixed by this migration - a product/policy question, not a bug): even after this
-- fix, algo_portfolio_snapshots' earliest surviving row is 2026-06-30, so MAX(total_portfolio_value)
-- still can't reflect this account's true 3-month peak ($76,021.61 on 2026-06-04) or true
-- all-time peak since account inception ($106,914.68 on 2024-06-06, verified via the same
-- Alpaca history endpoint). Whether the circuit breaker's "peak" should be backfilled to
-- reflect the account's full real history, or intentionally only reflects the window since this
-- table started being populated, is a deliberate choice for a human to make - not assumed here.

DELETE FROM algo_portfolio_snapshots
WHERE snapshot_date = '2026-06-29'
  AND total_portfolio_value = 85000.00
  AND cumulative_return_pct = -20.0000;

UPDATE algo_portfolio_snapshots
SET total_portfolio_value = 73060.87,
    total_equity = 73060.87,
    total_cash = 73060.87 - (total_portfolio_value - total_cash),
    updated_at = CURRENT_TIMESTAMP
WHERE snapshot_date = '2026-06-30'
  AND total_portfolio_value = 80000.00
  AND cumulative_return_pct = -20.0000;
