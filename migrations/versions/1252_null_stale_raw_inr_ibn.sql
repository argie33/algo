-- Migration 1252: Null out IBN's stale raw-INR financial-statement values
-- Date: 2026-08-29 (goal session continuation - see migration 1250's header and
-- [[inr_added_and_stale_raw_currency_cleanup_20260829]] for the full backstory)

-- Adding INR to MAJOR_CURRENCIES (utils/external/fx_rates.py, same session) does NOT
-- retroactively fix IBN's already-on-file historical rows: live-verified by actually
-- running the financial_statements loader via the pipeline scheduler after that fix
-- landed - IBN's SEC extraction this run returned nothing for any historical fiscal
-- year (they're already "on file" per this loader's incremental/watermark design, which
-- only re-touches the CURRENT period each run, same as every other statement table in
-- this codebase), and its current-period yfinance fallback has its OWN, separate
-- currency guard ("financialCurrency=INR has no USD conversion available") that isn't
-- wired to MAJOR_CURRENCIES at all - worth a follow-up investigation in its own right,
-- not fixed here. Net effect: IBN's raw, unconverted-INR historical rows (revenue in
-- the hundreds of billions, total_assets in the tens of trillions - real ICICI Bank
-- figures are ~2-3 orders of magnitude smaller in USD) were left untouched by that run
-- and would otherwise sit wrong indefinitely, same as the 10 symbols migration 1250
-- already cleaned up - IBN just wasn't among them because at the time it looked like a
-- pure "add the currency" fix would resolve it on the next run, which live-verification
-- disproved.
--
-- Scope: only annual_income_statement/quarterly_income_statement/quarterly_balance_sheet/
-- annual_cash_flow have matching raw rows for IBN (annual_balance_sheet and
-- quarterly_cash_flow have none) - confirmed via direct query before writing this.
-- KT (Korea Telecom, KRW) was live-checked for the same pattern and explicitly NOT
-- included here: KT has one bad FY2015 row (pre-KRW-whitelist raw value) sitting among
-- 9 other years of genuinely correct, already-converted KRW data - a blanket
-- data_unavailable=FALSE/reason IS NULL filter can't distinguish the one bad row from
-- the nine good ones without a magnitude check this migration doesn't attempt to
-- automate safely; left as a documented open item rather than risking a wrong bulk
-- UPDATE against real, correct data.

BEGIN;

UPDATE annual_income_statement
   SET revenue = NULL, net_income = NULL, gross_profit = NULL, operating_income = NULL,
       pretax_income = NULL, income_tax_expense = NULL, interest_expense = NULL,
       cost_of_revenue = NULL, research_development_expense = NULL,
       depreciation_expense = NULL, amortization_expense = NULL,
       eps = NULL, earnings_per_share = NULL, diluted_eps = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
 WHERE symbol = 'IBN' AND data_unavailable = FALSE AND reason IS NULL
   AND (revenue IS NOT NULL OR net_income IS NOT NULL);

UPDATE quarterly_income_statement
   SET revenue = NULL, net_income = NULL, gross_profit = NULL, operating_income = NULL,
       pretax_income = NULL, income_tax_expense = NULL, interest_expense = NULL,
       cost_of_revenue = NULL, research_development_expense = NULL,
       depreciation_expense = NULL, amortization_expense = NULL,
       eps = NULL, earnings_per_share = NULL, diluted_eps = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
 WHERE symbol = 'IBN' AND data_unavailable = FALSE AND reason IS NULL
   AND (revenue IS NOT NULL OR net_income IS NOT NULL);

UPDATE quarterly_balance_sheet
   SET total_assets = NULL, total_liabilities = NULL, stockholders_equity = NULL,
       current_assets = NULL, current_liabilities = NULL, cash_and_equivalents = NULL,
       accounts_receivable = NULL, inventory = NULL, ppe_net = NULL, goodwill = NULL,
       long_term_debt = NULL, short_term_debt = NULL,
       finance_lease_liability = NULL, operating_lease_liability = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
 WHERE symbol = 'IBN' AND data_unavailable = FALSE AND reason IS NULL
   AND (total_assets IS NOT NULL OR stockholders_equity IS NOT NULL);

UPDATE annual_cash_flow
   SET operating_cash_flow = NULL, investing_cash_flow = NULL, financing_cash_flow = NULL,
       capex = NULL, free_cash_flow = NULL, net_change_cash = NULL,
       dividends_paid = NULL, common_stock_repurchased = NULL, stock_based_compensation = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
 WHERE symbol = 'IBN' AND data_unavailable = FALSE AND reason IS NULL
   AND operating_cash_flow IS NOT NULL;

COMMIT;
