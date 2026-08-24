-- Migration 1220: Backfill data_unavailable=TRUE for financial-statement rows that have
-- no required metric populated (real-money-readiness audit, 2026-08-24)
--
-- loaders/load_financial_statements.py's ConsolidatedFinancialStatementsLoader.transform()
-- already marks a row data_unavailable=TRUE/reason='incomplete_sec_filing_{type}' when NONE
-- of the statement type's required metrics are populated (income: revenue/net_income;
-- balance: total_assets/stockholders_equity; cashflow: operating_cash_flow) - see that
-- method's "SPINOFF/INCOMPLETE DATA" branch, itself dated 2026-08-01 with several follow-up
-- fixes (2026-08-20/21/22) tightening the "already_available" rescue logic around it.
--
-- But that check only runs on rows the loader actually re-processes in a given run. Once a
-- fiscal year is "on file" for a symbol - real data or not - this loader's incremental fetch
-- never revisits it, so any row written before this defensive logic existed (or before its
-- later fixes landed) stays permanently mislabeled: data_unavailable=FALSE with every field
-- NULL, looking like "we have this data" when there is none. Same bug shape (and same
-- unreachable-by-normal-re-fetch root cause) as the EPS sweep in
-- [[eps_stale_historical_rows_sweep_fixed_20260824]]/migration history and the data_source
-- gap in commit 3be1a68ef.
--
-- Live-confirmed (local DB, 2026-08-24): 198 rows across all 6 statement tables, all with
-- data_source IS NULL (never even reached a source-tagging code path) and reason IS NULL.
-- Root symbol populations, all verified via stock_symbols/etf_symbols (not a live, ongoing
-- gap - all populations below stopped receiving new writes weeks before this migration):
--   - Currency-trust ETFs (FXA/FXB/FXC/FXE/FXF/FXY, in etf_symbols): stopped receiving writes
--     entirely as of 2026-06-19, well before this loader's exclude_etfs_from_symbols=True
--     default (loaders/helpers/sec_base.py) - historical debris from before that exclusion
--     existed, not a currently-recurring gap.
--   - Already-deactivated debt/preferred securities (stock_symbols.active=FALSE): AFGB,
--     AFGC, AFGD, AFGE, ATHS, BHFAL, DTB, DTG, DTK, DTW, DUKB, GENVR, SVA - subordinated
--     debentures/contingent value rights/halted foreign OTC, none of them equity, already
--     excluded from get_active_symbols() going forward.
--   - Active foreign ADS filers (20-F, sparser/differently-tagged XBRL than a 10-K, some
--     fiscal years genuinely have nothing extractable): BCH, BSAC, EC, TLK, UGP.
--   - Active US small-caps with real gaps in specific older fiscal years: MFIN, MYSE.
--
-- Not touching rows where data_source IS NOT NULL (those went through a real tagging path
-- and are out of scope here) or where reason IS NOT NULL (already carries an explanation).

UPDATE annual_income_statement
   SET data_unavailable = TRUE, reason = 'incomplete_sec_filing_income'
 WHERE data_unavailable = FALSE AND reason IS NULL AND data_source IS NULL
   AND revenue IS NULL AND net_income IS NULL;

UPDATE quarterly_income_statement
   SET data_unavailable = TRUE, reason = 'incomplete_sec_filing_income'
 WHERE data_unavailable = FALSE AND reason IS NULL AND data_source IS NULL
   AND revenue IS NULL AND net_income IS NULL;

UPDATE annual_balance_sheet
   SET data_unavailable = TRUE, reason = 'incomplete_sec_filing_balance'
 WHERE data_unavailable = FALSE AND reason IS NULL AND data_source IS NULL
   AND total_assets IS NULL AND stockholders_equity IS NULL;

UPDATE quarterly_balance_sheet
   SET data_unavailable = TRUE, reason = 'incomplete_sec_filing_balance'
 WHERE data_unavailable = FALSE AND reason IS NULL AND data_source IS NULL
   AND total_assets IS NULL AND stockholders_equity IS NULL;

UPDATE annual_cash_flow
   SET data_unavailable = TRUE, reason = 'incomplete_sec_filing_cashflow'
 WHERE data_unavailable = FALSE AND reason IS NULL AND data_source IS NULL
   AND operating_cash_flow IS NULL;

UPDATE quarterly_cash_flow
   SET data_unavailable = TRUE, reason = 'incomplete_sec_filing_cashflow'
 WHERE data_unavailable = FALSE AND reason IS NULL AND data_source IS NULL
   AND operating_cash_flow IS NULL;
