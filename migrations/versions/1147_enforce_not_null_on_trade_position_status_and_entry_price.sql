-- Migration 1147: Enforce NOT NULL on algo_trades.status, algo_positions.status,
-- algo_positions.avg_entry_price
-- Date: 2026-07-21
--
-- ROOT CAUSE (financial-integrity audit): algo_trades and algo_positions - the two tables
-- that record what the system believes it owns and what it paid - had zero DB-level CHECK
-- or NOT NULL enforcement on their status/price columns beyond a handful of NOT NULL
-- columns set at original table creation. Every status-gated code path in this codebase
-- (executor, exit handlers, MarketEventHandler halt logic, reconciliation, dashboard
-- panels) assumes `status` is always one of a small known set of strings and that
-- avg_entry_price is always populated for a position row - a NULL in either would silently
-- fall through every explicit `status = 'open'` / `status IN (...)` check (the exact failure
-- mode already found and fixed once for a different status-string bug: MarketEventHandler
-- halting positions with status='open' when the docstring's stale definition assumed
-- 'pending'). Verified 2026-07-21 against the live local DB: zero existing NULLs in any of
-- these three columns, so this is purely additive - no existing rows are affected, and no
-- code path in this repo has ever intentionally left these NULL (grep across algo/trading,
-- algo/orchestrator, algo/infrastructure shows status is always assigned an explicit string
-- on every INSERT/UPDATE).
--
-- SCOPED CONSERVATIVELY: NOT NULL only, not a value-enum CHECK constraint. The full set of
-- historically-used status strings ('open', 'closed', 'pending', 'cancelled', 'paper_open',
-- 'paper_pending') was not confirmed exhaustively per-table, so a CHECK IN (...) constraint
-- risked being wrong and rejecting a legitimate future write - worse than the current gap.
-- NOT NULL carries no such risk: every code path already sets this field explicitly.
--
-- algo_trades.entry_price/entry_quantity and algo_positions.quantity/entry_price/symbol
-- were already NOT NULL from earlier migrations - not touched here.
-- algo_positions.position_value intentionally left nullable: it can legitimately be
-- transiently unknown between price updates, unlike status/avg_entry_price.

BEGIN;

ALTER TABLE algo_trades ALTER COLUMN status SET NOT NULL;
ALTER TABLE algo_positions ALTER COLUMN status SET NOT NULL;
ALTER TABLE algo_positions ALTER COLUMN avg_entry_price SET NOT NULL;

COMMIT;
