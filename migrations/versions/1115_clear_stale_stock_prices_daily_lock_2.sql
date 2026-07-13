-- Migration 1115: Clear a second stale stock_prices_daily row-lock
--
-- Commit 0916bac77 fixed loaders/load_prices.py's lock-release path, but that fix only
-- takes effect once the ECS task image running it is rebuilt/redeployed. A pipeline
-- execution (post-all-fixes-verify-1783986365) ran stock_prices_daily using the
-- still-old image after the fix was merged but before "Deploy ECS Docker Image" actually
-- completed (its queued run kept losing the shared deploy concurrency group to newer
-- pushes -- see deploy-all-infrastructure.yml history around 2026-07-13 23:44-23:52
-- UTC), so it hit the exact same pre-fix bug and left another stale lock row behind.
--
-- Same safe, bounded pattern as migration 1114: only clears rows already locked more
-- than 10 minutes ago, so this can never touch a genuinely in-progress run.
-- "Deploy ECS Docker Image" has since completed successfully with the real fix, so this
-- should be the last time this specific cleanup is needed.

DELETE FROM loader_execution_locks
WHERE loader_name = 'stock_prices_daily'
  AND locked_at < NOW() - INTERVAL '10 minutes';
