-- Migration 1253: correct bookkeeping on rows carrying the orphaned
-- 'currency_conversion_bug_remediation_20260819' reason marker across all 6 SEC statement
-- tables, where every scored column is already NULL.
-- Date: 2026-08-29 (goal session: "keep working through the data issues" full-data pass,
-- continuation of migration 1250's own currency-remediation sweep)

-- ROOT CAUSE: migration 1250's WHERE clause required `reason IS NULL` (it only targeted rows
-- that looked fine but were secretly poisoned with a live wrong value). That clause correctly
-- excluded a DIFFERENT, larger population this pass found: rows an even earlier, undocumented
-- one-off remediation (zero code references anywhere in this repo, `git grep -w
-- currency_conversion_bug_remediation_20260819` returns nothing) had already tagged with this
-- reason string, but WITHOUT setting data_unavailable = TRUE and without ever nulling the
-- (already-NULL) values - live-confirmed: every single one of the 211 affected rows across
-- annual_income_statement (46), annual_balance_sheet (77), and annual_cash_flow (88) has every
-- scored column NULL already (verified via an exhaustive OR-across-all-columns count = 0 for
-- each table). This is NOT the "silently wrong number" bug class migration 1250/1252 fixed -
-- there is no live corrupted value being served here to null out. It IS a real, if lower-
-- severity, bug: data_unavailable = FALSE on the overwhelming majority of these rows (198/211)
-- tells every downstream consumer that gates on that flag alone (without also checking the
-- individual columns for NULL, the same "new field added to the success path, fallback never
-- updated" failure shape documented elsewhere in this file's own history) that the row is
-- real, available data - it is not. The stale reason string itself is also a real coverage-
-- audit hazard: scripts/audit_unavailable_reasons.py (and any future "what's still missing for
-- our scores" sweep modeled on it) has no way to recognize this orphaned one-off label as
-- equivalent to the "genuinely incomplete SEC filing" case every other row in these tables
-- already uses a real, current reason for - same failure shape as the "Other" bucket
-- miscategorization already fixed once this session for the Scores Data Coverage dashboard.
--
-- Symbol/currency detail is irrelevant to this specific fix (unlike 1250/1252): since every
-- value is already NULL, there is nothing to convert or null-out value-wise - this migration
-- only corrects the data_unavailable flag and replaces the non-standard reason string with the
-- exact same reason each table already uses, at far higher volume, for "no usable data landed
-- for this (symbol, fiscal_year) at all" (incomplete_sec_filing_income: 3,322 existing rows;
-- incomplete_sec_filing_balance: 11 existing rows; incomplete_sec_filing_cashflow: 2,548
-- existing rows - see this same migrations/versions/ directory's own recent 1248/1249 for the
-- income/cashflow precedent). Whether any of these specific symbols' underlying currency-guard
-- gap is itself now closable (e.g. HMC/JPY, KT/SKM/KRW, LU/CNY are all already-whitelisted
-- currencies that could in principle be re-extracted and actually populated) is a SEPARATE,
-- follow-up question for the financial_statements loader/backfill pipeline, not this migration
-- - this only fixes the bookkeeping inconsistency on rows that currently have nothing to show
-- for themselves regardless of currency.

BEGIN;

UPDATE annual_income_statement
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_income'
 WHERE reason = 'currency_conversion_bug_remediation_20260819'
   AND revenue IS NULL AND net_income IS NULL AND gross_profit IS NULL
   AND operating_income IS NULL AND eps IS NULL AND earnings_per_share IS NULL
   AND diluted_eps IS NULL;

UPDATE annual_balance_sheet
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_balance'
 WHERE reason = 'currency_conversion_bug_remediation_20260819'
   AND total_assets IS NULL AND stockholders_equity IS NULL
   AND total_liabilities IS NULL AND current_assets IS NULL;

UPDATE annual_cash_flow
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_cashflow'
 WHERE reason = 'currency_conversion_bug_remediation_20260819'
   AND operating_cash_flow IS NULL AND capex IS NULL
   AND free_cash_flow IS NULL AND investing_cash_flow IS NULL;

COMMIT;
