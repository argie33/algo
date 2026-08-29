-- Migration 1248: null out phantom "current fiscal year" annual_income_statement rows that
-- are actually just that symbol's own Q1 quarterly figures mislabeled as a full year.
--
-- Root cause (goal session 2026-08-29, composite-score validation against real data):
-- utils/external/sec_statements.py's period=="annual" span_days<330 filter (added 2026-08-09,
-- the ORLY fix) correctly rejects short-duration facts from a FRESH extraction today - live-
-- verified via a real SEC pull that get_income_statement(client, 'META', period='annual') no
-- longer returns any FY2026 row at all (META's real FY2026 10-K hasn't been filed - fiscal year
-- still in progress). But the loader's upsert only ever INSERTs/UPDATEs rows a fresh extraction
-- actually produces - it never clears a (symbol, fiscal_year) row that a corrected extraction
-- stops producing. So annual_income_statement rows written under whatever bug predated that
-- fix (or any earlier equivalent gap) are still sitting in the DB as data_unavailable=FALSE,
-- silently masquerading as real annual totals.
--
-- Live-confirmed via META: annual_income_statement.fiscal_year=2026 has revenue=$56,311,000,000
-- and net_income=$26,773,000,000 - EXACTLY equal to quarterly_income_statement's own
-- (fiscal_year=2026, fiscal_quarter=1) row for META, to the dollar. Q1 is unaffected by the
-- separate cumulative-vs-discrete quarterly bug fixed earlier this same session (a fiscal
-- year's own Q1 is always discrete by construction), so it's a reliable, unambiguous control:
-- a REAL full-year duration total can never legitimately equal a REAL single-quarter duration
-- total for a continuing operating company. Downstream impact: growth_metrics.revenue_growth_1y
-- (offset-1 CAGR between the two most recent annual_income_statement rows) computed
-- (56.311B - 200.966B) / 200.966B = -71.98% for META against a real FY2025 base - a company
-- whose real revenue grew ~20%+ YoY every year on record. The same whole-row-is-a-Q1-copy
-- pattern (revenue AND net_income both match to the dollar) was confirmed across a random
-- sample of 10 other affected symbols (ELMT, KSCP, LB, RDIB, GDRX, GENB, LILAK, MRP, LLYVA,
-- LPRO), so the whole row - not just revenue - is nulled via data_unavailable, not a
-- single-column patch.
--
-- Scope: fiscal_year=2026 only (312 symbols) - the current, unambiguously-still-in-progress
-- fiscal year for the overwhelming majority of the universe (calendar-year filers). Matches for
-- OLDER fiscal years (2008-2025, ~137 more rows) were deliberately NOT included here: some of
-- those are more likely genuine short "stub" fiscal-year filings (fiscal-year-end changes,
-- post-spinoff first partial year) that can legitimately be short - unlike a still-in-progress
-- current year, they need individual per-symbol verification before nulling (same caution this
-- file's own migration history already applies - see 1225/1226/1227's per-symbol VALUES lists).
-- annual_balance_sheet/annual_cash_flow show a similar signature (619 / 2735 matches against
-- their own Q1 rows) but are NOT included here either - unlike income-statement duration facts,
-- a balance sheet is an instant snapshot, and a real March/April-fiscal-year-end company can
-- legitimately have its true annual year-end balance coincide with what's labeled "Q1" - that
-- ambiguity needs its own separate, more careful pass, not a blanket condition.
--
-- The condition below is a computed match (not a hardcoded per-symbol list, given the volume)
-- but is exactly the mechanical signature described above: same symbol, fiscal_year=2026,
-- annual revenue currently marked available, and equal (within 1%, to absorb any stray
-- rounding/FX-cache rebasing) to that symbol's own real Q1 2026 quarterly revenue.

UPDATE annual_income_statement ais
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_income'
  FROM quarterly_income_statement q
 WHERE q.symbol = ais.symbol
   AND q.fiscal_year = ais.fiscal_year
   AND q.fiscal_quarter = 1
   AND ais.fiscal_year = 2026
   AND ais.data_unavailable = FALSE
   AND ais.revenue IS NOT NULL AND ais.revenue > 0
   AND q.revenue IS NOT NULL AND q.revenue > 0
   AND abs(ais.revenue - q.revenue) / q.revenue < 0.01;
