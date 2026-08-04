-- Migration 1196: Add symbols_failed to data_loader_status
--
-- ISSUE: loaders/runner.py computes an accurate per-run symbols_failed count from the
-- loader's own stats and passes it to LoaderStatusManager.mark_completed(symbols_failed=...),
-- but mark_completed() only logger.warning()s that count - it was never persisted to any DB
-- column. A loader that "completes" with e.g. 40 individual symbol failures under its
-- max_fail_rate threshold has that count permanently discarded, invisible anywhere except
-- grepping application logs. consecutive_failures only tracks whole-run failure streaks, not
-- per-run partial-failure counts, so a loader that partially fails every single run (never
-- crossing the fail-rate threshold, never incrementing consecutive_failures) looks identical
-- to a perfectly healthy one in the dashboard/API today.
--
-- FIX: persist the count mark_completed() already receives.

ALTER TABLE data_loader_status ADD COLUMN IF NOT EXISTS symbols_failed INTEGER;

COMMENT ON COLUMN data_loader_status.symbols_failed IS
    'Count of symbols that failed to load on the most recent COMPLETED run (partial-success visibility) - NULL means no failures reported or not tracked by this loader. Distinct from consecutive_failures, which tracks whole-run failure streaks.';
