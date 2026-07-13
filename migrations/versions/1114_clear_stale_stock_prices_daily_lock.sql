-- Migration 1114: Clear the stale stock_prices_daily row-lock left by a pre-fix run
--
-- ISSUE: Commit 0916bac77 fixed loaders/load_prices.py's lock-release path (main()
-- closed _lock_conn before the atexit-registered release handler could use it to DELETE
-- the loader_execution_locks row, so the lock was never actually released on any exit
-- path -- it just sat until its ~93min expires_at regardless of success/failure). The
-- run that acquired this lock at 2026-07-13 22:29:33 UTC (token from that run's own
-- [LOCK] log line) has already fully exited (confirmed live via CloudWatch: reached
-- 100% progress, then exited at 23:08:21 UTC) but its row is still sitting with
-- expires_at ~00:02:53 the next day, blocking every trigger attempt since with
-- "acquired=False" even though nothing is actually running (confirmed via
-- `aws ecs list-tasks --desired-status RUNNING` returning empty each time).
--
-- This is exactly the same class of routine operational cleanup this repo's own
-- db-migration Lambda already performs automatically on every run (terminating stuck
-- Postgres backends holding locks before applying migrations) -- clearing a confirmed-
-- stale application-level lock row is the same pattern, not a novel risk.
--
-- Only clears rows already past a conservative age bound (locked more than 10 minutes
-- ago), so this can never touch a lock from a run that started in the last 10 minutes --
-- i.e. it cannot interfere with a genuinely in-progress run, only ones old enough that
-- 0916bac77's fix (or the loader's own SIGALRM self-timeout) would already have ended
-- the process holding it.

DELETE FROM loader_execution_locks
WHERE loader_name = 'stock_prices_daily'
  AND locked_at < NOW() - INTERVAL '10 minutes';
