-- Migration 1171: Add shares_outstanding_basic to annual/quarterly income statement
--
-- ISSUE: sec_statements.py's get_income_statement() has fetched the real, officially-
-- reported "WeightedAverageNumberOfSharesOutstandingBasic" XBRL concept from SEC on every
-- run since this module was written, but load_financial_statements.py's field_mapping never
-- pointed it at a column - unmapped keys are silently dropped by transform(), so this real
-- SEC data was fetched and thrown away every run. Meanwhile load_sec_valuations.py's own
-- docstring claims shares outstanding comes from "WeightedAverageNumberOfSharesOutstandingBasic
-- (from SEC)" but the actual code never reads it - it instead derives shares_out = abs(net_income
-- / eps), a mathematically inferior proxy that loses precision to EPS's 2-decimal rounding
-- (material for large-caps with billions of shares), with a company_info_sec fallback.
--
-- FIX: give the real reported figure a destination column so load_sec_valuations.py can prefer
-- it over the derived proxy.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS shares_outstanding_basic NUMERIC;
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS shares_outstanding_basic NUMERIC;

COMMENT ON COLUMN annual_income_statement.shares_outstanding_basic IS
    'Real SEC XBRL WeightedAverageNumberOfSharesOutstandingBasic concept - the officially-reported weighted-average basic share count for the fiscal year, not a derived/inferred value.';
COMMENT ON COLUMN quarterly_income_statement.shares_outstanding_basic IS
    'Real SEC XBRL WeightedAverageNumberOfSharesOutstandingBasic concept - the officially-reported weighted-average basic share count for the fiscal quarter, not a derived/inferred value.';
