-- Migration 1279: correct bookkeeping on orphaned "hollow" rows in the 3 annual SEC
-- statement tables - real fiscal_year rows carrying data_unavailable = FALSE (meaning "we
-- have real data") but with every scored financial column NULL.
-- Date: 2026-09-10 (goal session: "missing SEC/XBRL data under 500" push,
-- assume-memory-is-wrong re-verification pass)
--
-- ROOT CAUSE: same bug class as migrations 1248/1250/1252/1253/1261 - a symbol/fiscal_year
-- combination was fetched and written by an OLDER version of loaders/load_financial_
-- statements.py's transform() (or a since-removed code path) that stored a "found nothing
-- usable" row without ever setting data_unavailable = TRUE. Live-confirmed via a direct
-- fetch_incremental()+transform() call against CURRENT code for 3 of these symbols (AIIR,
-- VRXA, WATR): today's loader produces ONLY a single fiscal_year=0
-- data_unavailable=TRUE/'no_annual_balance_data_in_sec_edgar_reit_or_special_entity' marker
-- for the whole symbol - it never revisits or rewrites the stale per-fiscal-year rows below,
-- so they are pure historical debris the current code can no longer reach or self-correct
-- (nothing re-fetches a specific old fiscal_year once the loader's incremental watermark has
-- moved past it). annual_balance_sheet alone has 195 such rows across 52 symbols - including
-- well-known FPIs already documented elsewhere in this migrations/versions/ history as having
-- "self-corrected" (BMA/LOMA/CEPU, per load_financial_statements.py's 2026-09-02 fix comment)
-- alongside others that evidently never did (CIG/GGB/STNE/SUZ/ABEV/VIV/PAGS/PAC/CEPU/BBAR and
-- more), plus a handful of unrelated small/recent filers (AIIR/BIOT/IMC/PSQL/RPGL/VRXA/WATR/
-- FTRK/GCDT/TBBB/TDIC/SVRE/AUNA/HONIV) with no shared root cause beyond "an old run wrote a
-- hollow available row and nothing has touched it since." annual_income_statement (20
-- rows/9 symbols) and annual_cash_flow (66 rows/21 symbols) have smaller populations of the
-- exact same shape.
--
-- Same reasoning as 1253: there is nothing to convert or backfill value-wise (every scored
-- column is already NULL), so this is purely a bookkeeping fix - flip data_unavailable to
-- TRUE and replace the misleading "no reason recorded" state with the same generic
-- incomplete_sec_filing_{type} label these tables already use, at far higher volume, for
-- "no usable data landed for this (symbol, fiscal_year) at all". This closes the
-- 'no_recent_balance_sheet_data_reported' row-level quality_metrics/value_metrics/
-- growth_metrics gap this bug was indirectly causing for the balance-sheet subset (a symbol
-- with ANY hollow-but-"available" row was invisible to the "does this symbol have EVER-real
-- data" checks these consumers run) without touching any currently-reachable/still-live
-- extraction logic.

BEGIN;

UPDATE annual_balance_sheet
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_balance'
 WHERE data_unavailable = FALSE
   AND fiscal_year != 0
   AND total_assets IS NULL AND stockholders_equity IS NULL
   AND total_liabilities IS NULL AND current_assets IS NULL;

UPDATE annual_income_statement
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_income'
 WHERE data_unavailable = FALSE
   AND fiscal_year != 0
   AND revenue IS NULL AND net_income IS NULL AND gross_profit IS NULL
   AND operating_income IS NULL AND eps IS NULL AND earnings_per_share IS NULL
   AND diluted_eps IS NULL;

UPDATE annual_cash_flow
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_cashflow'
 WHERE data_unavailable = FALSE
   AND fiscal_year != 0
   AND operating_cash_flow IS NULL AND capex IS NULL
   AND free_cash_flow IS NULL AND investing_cash_flow IS NULL;

COMMIT;
