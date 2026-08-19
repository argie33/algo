-- Migration 1210: Widen dividend_data.source from VARCHAR(50) to VARCHAR(80)
--
-- Live-confirmed 2026-08-19 (algo run review): load_dividend_data.py's
-- _extract_dividends_from_xbrl_concept() stamps source = f"SEC_XBRL_{concept_name}" (line
-- 256). For IFRS foreign private issuers, one of the two IFRS concepts tried -
-- DividendsRecognisedAsDistributionsToOwnersPerShare (see _IFRS_DIVIDEND_PER_SHARE_CONCEPTS
-- in that file) - produces "SEC_XBRL_DividendsRecognisedAsDistributionsToOwnersPerShare",
-- 59 characters, over the 50-char limit migration 1155 gave this column. Every IFRS filer
-- whose dividend facts resolve through that concept fails outright at the COPY step with
-- "value too long for type character varying(50)", losing the whole dividend_data row for
-- that symbol on every run, not just this one field - not a one-off, a permanent failure
-- for any symbol that only tags dividends under this concept. Scheduler log 2026-08-19
-- shows dozens of real international dividend payers hitting this every run: VOD, RIO,
-- BHP, AZN, SAP, SAN, TTE, STLA, ING, BBVA, BTI, EQNR, TSM, and 40+ more.
--
-- 80 chars covers this concept (59) plus headroom for any longer us-gaap/ifrs-full concept
-- name SEC introduces later, without needing another migration for the same class of bug.

ALTER TABLE dividend_data ALTER COLUMN source TYPE VARCHAR(80);
