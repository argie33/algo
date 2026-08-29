-- Migration 1250: Null out stale raw-local-currency financial-statement values for
-- confirmed non-major-currency foreign filers, across all 6 statement tables.
-- Date: 2026-08-29 (goal session: "keep working through the data issues" full-data pass)
-- (Numbered 1250, not 1237 - the shared local DB already had 1237-1249 applied by
-- concurrent sessions whose migration files never landed in this worktree's git
-- history; renumbered to avoid collision, same class of issue documented in
-- migration 1236's own header comment.)

-- ROOT CAUSE: utils/external/sec_statements.py's per-concept currency guard (see
-- utils/external/fx_rates.py's MAJOR_CURRENCIES docstring history) only rejects a
-- non-USD unit going forward, from whenever the guard for that specific currency was
-- added. Rows written by an EARLIER, pre-guard code version had already stored the
-- filer's raw home-currency figure directly as if it were USD - "once real, always
-- real" preserve_on_missing_fields logic (loaders/load_financial_statements.py) then
-- protects that wrong value from ever being overwritten by a later (correctly empty)
-- fetch, because the guard makes every subsequent fetch return None for the
-- unwhitelisted currency and None never overwrites a preserved value. Same bug shape
-- already fixed once for CNY (GDS) and ZAR (HMY) - see [[cny_currency_conversion_missing_stale_unconverted_values_20260820]]
-- / [[zar_currency_conversion_fixed_20260822]] in memory - but this pass found it is
-- NOT limited to income statements or to the symbols/currencies those two fixes
-- covered: a "currency_conversion_bug_remediation_20260819" reason marker sitting on
-- annual_income_statement (itself an orphaned one-off remediation from a prior
-- session - zero code references, see test_scores_coverage_order_col_and_unmapped_reasons_20260821.py)
-- named 14 symbols whose CURRENT fiscal years are correctly blocked, but whose OLDER
-- fiscal years - and, for several of them, ALL 6 statement tables, not just income -
-- still carry live, non-null, data_unavailable=FALSE raw-currency values that were
-- never cleaned up.
--
-- Live-verified per symbol (magnitude cross-check against each company's known real
-- USD-equivalent financials - same discipline as the CNY/ZAR fixes):
--   - BAK  (Braskem, Brazil/BRL):        FY2015 revenue 46.88B matches Braskem's real
--     reported BRL 45.4B - stored raw, not divided by BRL/USD (~3.9 in 2015).
--   - BSAC (Banco Santander Chile/CLP):  net_income ~450B-1,021B, Chile-scale CLP
--     magnitudes; CLP still 404s on Frankfurter (structural, not fixable here).
--   - EDN/GGAL/SUPV/TEO/TGS (Argentina/ARS): revenue/net_income in the tens-of-billions
--     to trillions range tracking Argentina's real hyperinflation trajectory - raw ARS,
--     not USD. Frankfurter stops serving ARS after 2020-10-30 entirely (structural gap
--     for recent years on top of the volatility problem).
--   - HEPS/TKC (Hepsiburada/Turkcell, Turkey/TRY): TRY moved 20%-154% YoY 2019-2025
--     (live Frankfurter check) - far past the ~8%-22% bar CNY/ZAR/MXN precedent uses.
--   - TV (Grupo Televisa, Mexico/MXN):    same MXN already declined for CNY/ZAR-bar
--     volatility (22.4% YoY, [[zar_currency_conversion_fixed_20260822]]).
-- None of BRL/CLP/ARS/TRY/MXN clear the volatility (or, for CLP/ARS, source-
-- availability) bar the live-verification discipline in fx_rates.py requires before
-- whitelisting a currency - see that module's 2026-08-29 docstring addition. These
-- values cannot be safely converted, only detected and nulled - same "honest NULL over
-- a silently wrong number" rule the original KRW/JPY guard was built on.
--
-- DXF (Eason Technology) and KT (KT Corp)/IBN (ICICI Bank) intentionally excluded from
-- this cleanup: DXF's reporting currency is not yet confirmed (ambiguous small-cap,
-- needs its own investigation before touching); KT is KRW (already whitelisted,
-- self-heals via the existing already_available rescue on next loader run - only a
-- single stale FY2015 raw-value row remains there, low-priority/old); IBN is INR,
-- fixed properly this same session by adding INR to MAJOR_CURRENCIES (see
-- utils/external/fx_rates.py) rather than nulling its real, now-convertible data.
-- KSPI excluded: it has zero historical extraction even pre-guard (a different, deeper
-- ifrs-full concept-extraction gap, not a currency-guard case) - nothing to null.
--
-- Only touches rows currently data_unavailable=FALSE AND reason IS NULL (i.e. rows
-- that look fine but are the pre-guard poisoned kind) for these 10 confirmed symbols -
-- never rows already correctly marked unavailable by the guard itself, and never any
-- other symbol. Share-count columns (shares_outstanding_basic/dei/diluted) are NOT
-- currency-denominated and are left untouched.

BEGIN;

CREATE TEMP TABLE _poisoned_currency_symbols (symbol TEXT PRIMARY KEY);
INSERT INTO _poisoned_currency_symbols (symbol) VALUES
    ('BAK'), ('BSAC'), ('EDN'), ('GGAL'), ('HEPS'), ('SUPV'), ('TEO'), ('TGS'), ('TKC'), ('TV');

UPDATE annual_income_statement a
   SET revenue = NULL, net_income = NULL, gross_profit = NULL, operating_income = NULL,
       pretax_income = NULL, income_tax_expense = NULL, interest_expense = NULL,
       cost_of_revenue = NULL, research_development_expense = NULL,
       depreciation_expense = NULL, amortization_expense = NULL,
       eps = NULL, earnings_per_share = NULL, diluted_eps = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
  FROM _poisoned_currency_symbols p
 WHERE a.symbol = p.symbol AND a.data_unavailable = FALSE AND a.reason IS NULL
   AND (a.revenue IS NOT NULL OR a.net_income IS NOT NULL);

UPDATE quarterly_income_statement a
   SET revenue = NULL, net_income = NULL, gross_profit = NULL, operating_income = NULL,
       pretax_income = NULL, income_tax_expense = NULL, interest_expense = NULL,
       cost_of_revenue = NULL, research_development_expense = NULL,
       depreciation_expense = NULL, amortization_expense = NULL,
       eps = NULL, earnings_per_share = NULL, diluted_eps = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
  FROM _poisoned_currency_symbols p
 WHERE a.symbol = p.symbol AND a.data_unavailable = FALSE AND a.reason IS NULL
   AND (a.revenue IS NOT NULL OR a.net_income IS NOT NULL);

UPDATE annual_balance_sheet a
   SET total_assets = NULL, total_liabilities = NULL, stockholders_equity = NULL,
       current_assets = NULL, current_liabilities = NULL, cash_and_equivalents = NULL,
       accounts_receivable = NULL, inventory = NULL, ppe_net = NULL, goodwill = NULL,
       long_term_debt = NULL, short_term_debt = NULL, retained_earnings = NULL,
       finance_lease_liability = NULL, operating_lease_liability = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
  FROM _poisoned_currency_symbols p
 WHERE a.symbol = p.symbol AND a.data_unavailable = FALSE AND a.reason IS NULL
   AND (a.total_assets IS NOT NULL OR a.stockholders_equity IS NOT NULL);

UPDATE quarterly_balance_sheet a
   SET total_assets = NULL, total_liabilities = NULL, stockholders_equity = NULL,
       current_assets = NULL, current_liabilities = NULL, cash_and_equivalents = NULL,
       accounts_receivable = NULL, inventory = NULL, ppe_net = NULL, goodwill = NULL,
       long_term_debt = NULL, short_term_debt = NULL,
       finance_lease_liability = NULL, operating_lease_liability = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
  FROM _poisoned_currency_symbols p
 WHERE a.symbol = p.symbol AND a.data_unavailable = FALSE AND a.reason IS NULL
   AND (a.total_assets IS NOT NULL OR a.stockholders_equity IS NOT NULL);

UPDATE annual_cash_flow a
   SET operating_cash_flow = NULL, investing_cash_flow = NULL, financing_cash_flow = NULL,
       capex = NULL, free_cash_flow = NULL, net_change_cash = NULL,
       dividends_paid = NULL, common_stock_repurchased = NULL, stock_based_compensation = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
  FROM _poisoned_currency_symbols p
 WHERE a.symbol = p.symbol AND a.data_unavailable = FALSE AND a.reason IS NULL
   AND a.operating_cash_flow IS NOT NULL;

UPDATE quarterly_cash_flow a
   SET operating_cash_flow = NULL, investing_cash_flow = NULL, financing_cash_flow = NULL,
       capex = NULL, free_cash_flow = NULL, net_change_cash = NULL,
       dividends_paid = NULL, common_stock_repurchased = NULL, stock_based_compensation = NULL,
       data_unavailable = TRUE, reason = 'raw_unconverted_currency_stale_value_20260829'
  FROM _poisoned_currency_symbols p
 WHERE a.symbol = p.symbol AND a.data_unavailable = FALSE AND a.reason IS NULL
   AND a.operating_cash_flow IS NOT NULL;

DROP TABLE _poisoned_currency_symbols;

COMMIT;
