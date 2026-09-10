-- Migration 1266: Add retained_earnings to quarterly_balance_sheet
--
-- annual_balance_sheet has had a retained_earnings column since migration 1234 (Altman
-- Z''-Score's Retained Earnings/Total Assets term). quarterly_balance_sheet never got the
-- equivalent - every quarterly balance-sheet fetch already pulls the real SEC-tagged
-- RetainedEarningsAccumulatedDeficit concept (sec_balance_sheet.py's get_balance_sheet()
-- concept list is shared with annual), but the value was discarded post-fetch with an
-- "Unmapped SEC field" warning on every symbol, every quarter, since there was no column to
-- write it to.
--
-- Same table/column shape as annual_balance_sheet.retained_earnings; same fix pattern as
-- accounts_payable (migration 1263) and noncontrolling_interest (migration 1265).

ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS retained_earnings NUMERIC(20, 2);

COMMENT ON COLUMN quarterly_balance_sheet.retained_earnings IS
    'Real SEC XBRL RetainedEarningsAccumulatedDeficit concept - was fetched but discarded every quarter before this column existed. Not yet used in any scoring/quality-pillar logic (no quarterly Altman Z-Score variant is computed anywhere in this codebase).';
