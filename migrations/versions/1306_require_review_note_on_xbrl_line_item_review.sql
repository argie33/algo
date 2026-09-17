-- Migration 1306: Require a real review_note whenever review_status != 'unreviewed'.
--
-- 2026-09-17: found 6,879 xbrl_yfinance_line_item_report rows marked reviewed_not_error by
-- scratch scripts that bypassed scripts/xbrl_line_item_review.py entirely (raw UPDATE statements,
-- reviewed_by values like "sweep_batch2_20260917" instead of a real identity - no such script is
-- checked into the repo, so there is nothing left to audit). Their only justification was
-- "consistent with this symbol's own multi-year trend" - that checks a number against its own
-- history, not against SEC or against why yfinance disagrees, and does not meet migration 1302's
-- own documented bar of a "human review verdict." Reverted to unreviewed (see git history /
-- session notes around 2026-09-17 for the correction).
--
-- scripts/xbrl_line_item_review.py now refuses a status change with no note (>=20 chars), but
-- that only stops misuse of that one tool - nothing stops another one-off script from doing raw
-- SQL again. This CHECK constraint is the actual backstop: the database itself now rejects any
-- non-'unreviewed' review_status with a null/short review_note, regardless of what wrote it.

BEGIN;

ALTER TABLE xbrl_yfinance_line_item_report
    ADD CONSTRAINT chk_xbrl_yf_line_item_review_note_required
        CHECK (review_status = 'unreviewed' OR (review_note IS NOT NULL AND length(trim(review_note)) >= 20));

COMMIT;
