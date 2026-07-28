-- Migration 1165: Drop dead order_execution_log table
--
-- Table exists in the DB (columns for slippage_bps, fill_rate_pct, execution_latency_ms,
-- retry_count, alpaca_order_id - looks designed for per-order execution-quality auditing)
-- but was never wired to any writer: 0 rows, zero references anywhere in the Python codebase
-- (lambda/api/, algo/, loaders/, scripts/), and no earlier migration file created it (it
-- predates this migration system or was created ad hoc outside it).
--
-- Its only references anywhere in the repo are 3 SELECT queries in webapp/lambda/routes/algo.js
-- - confirmed dead code (see feedback_webapp_lambda_is_dead_code memory: no Terraform resource,
-- no deploy workflow, never receives real traffic). Real per-order execution-quality auditing,
-- if wanted later, belongs on algo_trades/algo_position_sizing_audit or a newly-designed table
-- wired to TradeExecutor at write time - not a resurrection of this orphaned one.

DROP TABLE IF EXISTS order_execution_log;
