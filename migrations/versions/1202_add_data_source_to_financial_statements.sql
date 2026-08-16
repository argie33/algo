-- Migration 1202: Add data_source to the 6 SEC financial-statement tables
--
-- CONTEXT: loaders/load_financial_statements.py is being extended with a yfinance
-- fallback (utils/external/yfinance_financials.py) for the ~500-650 symbols/statement
-- combos where SEC EDGAR genuinely has no XBRL data at all (cik_not_found /
-- no_..._data_in_sec_edgar_reit_or_special_entity - REITs/trusts/SPVs/foreign filers
-- with sparse coverage, confirmed live 2026-08-16). Per this codebase's established
-- governance pattern (see value_metrics.data_source, and
-- tests/unit/test_company_info_sec_no_yfinance_pollution.py's explicit rule that
-- yfinance-sourced data must never be indistinguishable from SEC-audited data), every
-- row written by loaders/helpers/sec_base.py::SecEdgarStatementLoader must be tagged
-- with its real source so downstream consumers/dashboards can tell audited SEC figures
-- apart from a lower-fidelity yfinance fallback. Fallback only fires when SEC has
-- nothing at all for that symbol - never as a competing/overwriting source.

BEGIN;

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);
ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);
ALTER TABLE annual_cash_flow ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);
ALTER TABLE quarterly_cash_flow ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);

COMMIT;
