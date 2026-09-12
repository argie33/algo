-- Migration 1283: widen tiingo_backfill_status's status CHECK constraint to include
-- 'suspect_ticker_reuse'.
--
-- Added 2026-09-12 (methodology-foundation goal session, same day as 1282). Built
-- scripts/stooq_bulk_price_backfill.py to load a second, much stronger no-budget
-- survivorship-bias data source (Stooq's manually-downloaded bulk archive) using this same
-- status table so both scripts don't re-attempt each other's already-resolved symbols. That
-- script needs a fourth outcome beyond the original three: a candidate symbol whose archive
-- file shows trading data suspiciously close to "today" despite being marked inactive/
-- delisted in our own stock_symbols - almost certainly a ticker-reuse collision (e.g. this
-- archive's "WM" is Waste Management, not the real target Washington Mutual) rather than
-- real data for the entity our row refers to. Recording this distinctly (not as a bare
-- 'error') lets a future run skip past an already-flagged suspect instead of re-flagging it
-- every time, and gives a human reviewer a queryable list of exactly what needs manual
-- verification before ever being loaded.

ALTER TABLE tiingo_backfill_status DROP CONSTRAINT tiingo_backfill_status_status_check;

ALTER TABLE tiingo_backfill_status ADD CONSTRAINT tiingo_backfill_status_status_check
    CHECK (status IN ('backfilled', 'no_data_at_vendor', 'error', 'suspect_ticker_reuse'));
