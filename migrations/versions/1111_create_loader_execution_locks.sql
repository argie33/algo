-- Migration 1111: Create loader_execution_locks table for row-based mutual exclusion
--
-- ISSUE: loaders/load_prices.py used pg_try_advisory_lock() for mutual exclusion between
-- concurrent stock_prices_daily instances. Confirmed live 2026-07-13: two ECS tasks
-- (efe12da8..., started 21:48 UTC, and f674f20d..., started 21:59 UTC) both logged
-- "pg_try_advisory_lock('stock_prices_daily') acquired=True" with different backend_pid,
-- and both were actively processing symbols concurrently. PostgreSQL advisory locks are
-- held in server-local shared memory, not replicated/shared across physical instances or
-- connections -- RDS Proxy's connection pinning/multiplexing under concurrent load can
-- route different logical sessions in ways that break the single-server assumption
-- pg_try_advisory_lock depends on for correctness.
--
-- FIX: A row-based lock backed by an actual committed table row is immune to this class
-- of problem -- its correctness depends only on standard MVCC row visibility and atomic
-- UPDATE...WHERE semantics, not on which physical backend connection a session happens to
-- be pinned to. Any connection reading committed data through RDS Proxy sees the same row.

CREATE TABLE IF NOT EXISTS loader_execution_locks (
    loader_name TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE loader_execution_locks IS
    'Row-based mutual-exclusion lock for loaders, replacing pg_try_advisory_lock (unreliable '
    'through RDS Proxy connection pinning under concurrent load -- see migration 1111).';
