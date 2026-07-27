-- Migration 1158: Widen the "one live position per symbol" unique indexes to cover
-- every non-terminal status, not just the literal string 'open'.
--
-- ROOT CAUSE: Migration 007 added a partial UNIQUE INDEX on algo_trades(symbol) WHERE
-- status = 'open' specifically to stop duplicate open positions for the same symbol, and
-- algo/orchestrator/phase8_entry_execution.py's duplicate-entry guard cites it in a comment
-- as the DB-level mitigation for its own known-non-atomic check-then-insert race
-- ("Database UNIQUE constraint on (symbol, date, status='open') prevents actual
-- duplicates"). That claim is false for real (execution_mode="auto") trades: verified by
-- reading algo/trading/executor_entry_handler.py end to end, a live order that actually
-- fills never writes status='open' - it writes the broker-verified status literally
-- ("filled" or "partially_filled"; see _record_entry_phase's order_status = str(verified_status)
-- and _insert_trade_record's use of request.order_status). 'open' is written only by the
-- paper/dry execution_mode branch (executor.py's _submit_and_validate_order). So the one
-- partial index that exists never fires for a live order, and two concurrent live entries for
-- the same symbol (e.g. an orchestrator run racing a manual API trade from
-- lambda/api/routes/trades.py, which does insert status='open') can both land with no DB
-- error - confirmed by checking pg_constraint/pg_indexes on both tables: algo_positions has
-- no unique index on symbol at all, only a plain non-unique idx_algo_positions_symbol_status.
--
-- IMPACT: every downstream consumer of "the open position for this symbol" - exit_engine.py's
-- exit UPDATEs (`WHERE symbol = %s AND status = 'open'`, no LIMIT 1, would touch/miscount
-- multiple rows), alpaca_sync_manager.py's reconciliation SELECT, phase9 reconciliation -
-- assumes exactly one live row per symbol. This is a correctness gap on the exact table pair
-- (algo_trades/algo_positions) that migration 1147 called "what the system believes it owns
-- and what it paid", going into real-money trading.
--
-- FIX: replace the narrow status='open' partial index with one covering every non-terminal
-- status actually written by the codebase (grepped exhaustively across algo/trading,
-- algo/orchestrator, lambda/api/routes/trades.py): 'open', 'filled', 'partially_filled',
-- 'paper_pending', 'pending'. Terminal statuses ('closed', 'cancelled', 'rejected', 'expired',
-- 'invalid', 'unknown') are deliberately excluded so re-entry after a closed/failed trade is
-- never blocked. algo_positions only ever receives 'open' or 'paper_open' for a live row (see
-- executor_entry_handler.py's position_status assignment) plus 'closed' on exit, so its index
-- only needs those two.
--
-- Scoped like migration 1147: no CHECK/enum constraint (same reasoning - risk of rejecting a
-- legitimate future status string outweighs the benefit), just widening an existing partial
-- unique index to the statuses already in real use today.

BEGIN;

DROP INDEX IF EXISTS algo_trades_symbol_open_positions_idx;

CREATE UNIQUE INDEX IF NOT EXISTS algo_trades_symbol_live_status_idx
ON algo_trades(symbol)
WHERE status IN ('open', 'filled', 'partially_filled', 'paper_pending', 'pending');

COMMENT ON INDEX algo_trades_symbol_live_status_idx IS
'Partial unique index ensuring only ONE non-terminal (live) trade row per symbol.
Covers every status a real order can be inserted with (open/filled/partially_filled/
paper_pending/pending), not just "open" - see migration 1158 for why the original
migration-007 index never actually fired for live (execution_mode=auto) trades.';

CREATE UNIQUE INDEX IF NOT EXISTS algo_positions_symbol_live_status_idx
ON algo_positions(symbol)
WHERE status IN ('open', 'paper_open');

COMMENT ON INDEX algo_positions_symbol_live_status_idx IS
'Partial unique index ensuring only ONE live position per symbol (open or paper_open).
algo_positions previously had no uniqueness enforcement at all - see migration 1158.';

COMMIT;
