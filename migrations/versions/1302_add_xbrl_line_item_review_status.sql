-- Migration 1302: Persisted human-review state for xbrl_yfinance_line_item_report (migration 1300).
--
-- 2026-09-16 follow-up to the divergence-repair corruption incident (see
-- scripts/DIVERGENCE_REPAIR_POSTMORTEM.md): `divergent` alone is a binary "SEC and yfinance
-- disagree by more than X" flag, computed fresh by every scripts/xbrl_yfinance_crosscheck.py
-- run - it does NOT mean anyone has confirmed which source (if either) is actually wrong. The
-- incident happened because divergent=true got treated as "confirmed wrong, safe to overwrite."
-- Manual investigation work (scripts/categorize_remaining_divergences.py, the postmortem in
-- scripts/COMPLETE_FIX_STATUS_2026-09-16.md) has been happening since, but its conclusions were
-- only ever written to scratch JSON files and markdown prose - never back into this table - so
-- there was nowhere for the dashboard (or the next session) to read "someone already looked at
-- this row" back from. This column is that home.
--
-- review_status is deliberately NOT auto-populated from the existing postmortem docs: those
-- narrate findings by symbol in prose, without a reliable (our_table, our_field, fiscal_year)
-- key for every claim, and guessing at row identity to backfill this column would repeat the
-- exact "confidently wrong metadata" mistake the incident was about. Every row starts
-- 'unreviewed' and only moves via an explicit, row-identified marking (scripts/
-- xbrl_line_item_review.py) or resolves itself back to divergent=false next crosscheck run.

ALTER TABLE xbrl_yfinance_line_item_report
    ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) NOT NULL DEFAULT 'unreviewed'
        CHECK (review_status IN ('unreviewed', 'reviewed_not_error', 'reviewed_needs_fix', 'reviewed_fixed')),
    ADD COLUMN IF NOT EXISTS review_note TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(80);

-- A crosscheck re-run upserts existing (symbol, our_table, our_field, fiscal_year) rows (see
-- migration 1300's UNIQUE constraint) - reset review state back to 'unreviewed' whenever the
-- underlying comparison actually changes (new our_value/yfinance_value/divergent), so a stale
-- "reviewed_not_error" verdict can't silently keep covering for a since-changed number. A
-- re-upsert that reproduces the exact same comparison (nothing changed) leaves review state
-- alone.
COMMENT ON COLUMN xbrl_yfinance_line_item_report.review_status IS
    'Human review verdict on a divergent row, independent of the divergent flag itself. '
    'unreviewed = default, nobody has looked. reviewed_not_error = investigated, legitimate '
    'difference (restatement, reporting-timing, etc), not a bug. reviewed_needs_fix = '
    'investigated, confirmed wrong, fix not yet applied. reviewed_fixed = investigated, was '
    'wrong, source table has since been corrected - kept for audit trail even after the row '
    'stops being divergent on the next crosscheck run. Set only via scripts/'
    'xbrl_line_item_review.py, never by scripts/xbrl_yfinance_crosscheck.py itself.';

CREATE INDEX IF NOT EXISTS idx_xbrl_yf_line_item_review_status
    ON xbrl_yfinance_line_item_report(review_status) WHERE review_status != 'unreviewed';
