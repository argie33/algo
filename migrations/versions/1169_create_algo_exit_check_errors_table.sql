-- Migration 1169: Create algo_exit_check_errors audit table
--
-- ROOT CAUSE: exit_engine.py's check_and_execute_exits() catches per-trade exceptions
-- (bare `except Exception`), rolls back to a savepoint, increments a trade_errors counter,
-- and logs via logger.error/logger.critical - but never persists anything to the database.
-- For every scheduled/background orchestrator run (i.e. almost all of them - this is a
-- local-dev/cron-driven system, nobody has a terminal open watching stdout), that log line
-- is gone the moment the process exits. Confirmed live 2026-07-27: run
-- LOCAL-MORNING-20260727-112904-608395 reported "0 exits, 0 stop-raises, 7 errors" in
-- orchestrator_execution_log with zero further detail anywhere in the database - no way to
-- determine after the fact which positions failed their exit/stop-raise check or why.
--
-- This is a materially higher-stakes blind spot than the equivalent already-fixed gap for
-- entry rejections (algo_signal_rejections, see migration history / phase8_entry_execution.py
-- _log_signal_rejection): a failed entry means a missed opportunity, but a failed exit check
-- means an open position silently loses stop-loss/target/time-exit coverage for that run,
-- with real money at risk. Mirrors the same audit-table pattern used for algo_signal_rejections
-- so operators (and this codebase's own health checks) can query *why* after the fact instead
-- of only ever seeing an opaque error count.

BEGIN;

CREATE TABLE IF NOT EXISTS algo_exit_check_errors (
    id SERIAL PRIMARY KEY,
    error_date DATE NOT NULL,
    trade_id VARCHAR(64),
    position_id VARCHAR(64),
    symbol VARCHAR(20) NOT NULL,
    error_type VARCHAR(200) NOT NULL,
    error_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_algo_exit_check_errors_date ON algo_exit_check_errors(error_date);
CREATE INDEX IF NOT EXISTS idx_algo_exit_check_errors_symbol ON algo_exit_check_errors(symbol);

COMMIT;
