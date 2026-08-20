-- Migration 1212: Widen dividend_data.source from VARCHAR(80) to VARCHAR(120)
--
-- Live-confirmed 2026-08-19 (goal session continuation, live during a triggered dividend_data
-- backfill): migration 1210 widened this column to 80 chars to cover the longest per-share IFRS
-- concept name at the time (SEC_XBRL_DividendsRecognisedAsDistributionsToOwnersPerShare, 59
-- chars) - but the total-dollar fallback added the same day (commit e13d8edd8, after 1210 was
-- written) stamps source = f"SEC_XBRL_TOTAL_{concept_name}", a 15-char prefix instead of 9. For
-- DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities (the broadest IFRS
-- total-dividend concept, 67 chars), that's "SEC_XBRL_TOTAL_" + 67 = 82 chars - 2 over the
-- freshly-widened limit. Every real IFRS filer whose dividend facts resolve only through this
-- concept fails outright at the COPY step with "value too long for type character varying(80)",
-- losing the whole dividend_data row - live-confirmed BEPC, BVN, BWLP, CAAP, DEO, ENLT and more
-- hitting this on every run within minutes of the backfill starting.
--
-- 120 chars covers the current longest (82) with real headroom for any longer us-gaap/ifrs-full
-- concept name SEC introduces later, matching migration 1210's own stated intent of avoiding a
-- third migration for the same bug class.

ALTER TABLE dividend_data ALTER COLUMN source TYPE VARCHAR(120);
