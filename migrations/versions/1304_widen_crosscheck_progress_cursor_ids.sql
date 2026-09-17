-- Migration 1304: Widen xbrl_yfinance_crosscheck_progress to admit a second sweep cursor.
--
-- 2026-09-17, split out of 1303 deliberately: 1303 and this migration each touch exactly one
-- table so their AccessExclusiveLock windows never overlap two tables at once. Combining both
-- ALTERs into a single transaction deadlocked repeatedly (live-confirmed multiple times this
-- session) against the concurrently-running xbrl_yfinance_crosscheck.py sweep, whose own
-- per-symbol transaction touches xbrl_yfinance_line_item_report and (on cursor advance)
-- xbrl_yfinance_crosscheck_progress in the opposite order from a combined migration - a classic
-- AB-BA lock-ordering cycle, not fixable by retrying the same transaction shape.
--
-- Second sweep cursor row for the quarterly crosscheck (scripts/xbrl_yfinance_quarterly_crosscheck.py),
-- independent of the annual sweep's progress (id=1) since the quarterly universe/cadence differs.
-- The original CHECK (id = 1) only ever allowed a single row; widened to admit exactly these two
-- known consumers rather than dropped outright, so a future stray id=3 insert still fails loudly.
ALTER TABLE xbrl_yfinance_crosscheck_progress
    DROP CONSTRAINT IF EXISTS xbrl_yfinance_crosscheck_progress_id_check;
ALTER TABLE xbrl_yfinance_crosscheck_progress
    ADD CONSTRAINT xbrl_yfinance_crosscheck_progress_id_check CHECK (id IN (1, 2));

COMMENT ON COLUMN xbrl_yfinance_crosscheck_progress.id IS
    '1 = annual crosscheck sweep cursor (scripts/xbrl_yfinance_crosscheck.py). '
    '2 = quarterly crosscheck sweep cursor (scripts/xbrl_yfinance_quarterly_crosscheck.py).';
