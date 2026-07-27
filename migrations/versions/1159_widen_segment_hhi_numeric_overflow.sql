-- Migration 1159: Fix revenue_concentration_hhi NUMERIC precision overflow.
--
-- ROOT CAUSE: sec_segment_info (migration 1157) and sec_segment_metrics (migration 1150)
-- both declared revenue_concentration_hhi NUMERIC(5, 3) - max absolute value 99.999 - right
-- next to a comment on the same line documenting the real range as "0-10000, 10000=monopoly".
-- utils/external/sec_xbrl_segments.py._compute_herfindahl_index scales its output to 0-10000
-- exactly as documented (HHI = sum(share^2) * 10000), so any symbol with real segment
-- concentration data (anything above the ~1% HHI floor, i.e. virtually every multi-segment
-- filer) produces a value the column physically cannot store.
--
-- IMPACT: confirmed live against current code (2026-07-27) - load_sec_segment_info.py's raw
-- XBRL XML fallback now successfully parses real segment revenue for AAPL/MSFT/AMZN (HHI
-- 2900.952 / 3637.948 / 4368.18 respectively), but every single insert then fails at the DB
-- write with `psycopg2.errors.NumericValueOutOfRange`, crashing the whole loader run
-- ("N symbols failed-incomplete dataset"). This has silently defeated the entire raw-XBRL-XML
-- segment parsing effort (sessions 460 onward) end to end - the parser has never once
-- successfully written real segment data to either table; every existing row in
-- sec_segment_info is a stale data_unavailable marker from before the fallback existed.
--
-- FIX: widen both tables' revenue_concentration_hhi to NUMERIC(8, 3), matching the documented
-- 0-10000 range with the same 3 decimal places of precision.

BEGIN;

ALTER TABLE sec_segment_info
    ALTER COLUMN revenue_concentration_hhi TYPE NUMERIC(8, 3);

ALTER TABLE sec_segment_metrics
    ALTER COLUMN revenue_concentration_hhi TYPE NUMERIC(8, 3);

COMMIT;
