-- Migration 1197: Widen NUMERIC(16,2) financial-statement columns to NUMERIC(20,2)
--
-- ISSUE: annual_balance_sheet.{current_assets,stockholders_equity,total_assets,
-- total_liabilities} and annual_income_statement.{revenue,cost_of_revenue,gross_profit,
-- operating_income,net_income} are NUMERIC(16,2), capping magnitude under 10^14
-- (99,999,999,999,999.99). Live-caught 2026-08-04 reloading TLK (Telkom Indonesia):
-- COPY failed with "numeric field overflow ... must round to an absolute value less
-- than 10^14" on stockholders_equity=105,276,000,000,000 (IDR). Foreign filers that
-- report in a high-nominal-value local currency routinely exceed this - live-confirmed
-- also affects KEP (Korea Electric Power, KRW: total_liabilities ~205 trillion) and EC
-- (Ecopetrol, COP: revenue ~143 trillion, total_assets ~298 trillion) - real, large,
-- actively-traded companies, not an edge case. The load silently drops the ENTIRE
-- balance-sheet/income-statement row for these symbols (COPY of the whole batch rolls
-- back), which is the direct mechanism behind them showing "SEC data not available" on
-- the scores page despite SEC EDGAR having complete real data.
--
-- FIX: widen to NUMERIC(20,2) - 18 integer digits, headroom to ~10^18 - comfortably
-- covers any real company's financials in any live-traded currency (JPY/VND/IDR/KRW/COP
-- included) without risking a similar overflow again. Same treatment applied to the
-- quarterly tables' equivalent columns (the loader log showed quarterly_balance_sheet/
-- quarterly_income_statement failing on the same 3 symbols the same run) - quarterly_
-- income_statement.cost_of_revenue was already NUMERIC(20,2) from a prior fix of this
-- same class, confirming the precedent.

ALTER TABLE annual_balance_sheet
    ALTER COLUMN current_assets TYPE NUMERIC(20, 2),
    ALTER COLUMN stockholders_equity TYPE NUMERIC(20, 2),
    ALTER COLUMN total_assets TYPE NUMERIC(20, 2),
    ALTER COLUMN total_liabilities TYPE NUMERIC(20, 2);

ALTER TABLE annual_income_statement
    ALTER COLUMN revenue TYPE NUMERIC(20, 2),
    ALTER COLUMN cost_of_revenue TYPE NUMERIC(20, 2),
    ALTER COLUMN gross_profit TYPE NUMERIC(20, 2),
    ALTER COLUMN operating_income TYPE NUMERIC(20, 2),
    ALTER COLUMN net_income TYPE NUMERIC(20, 2);

ALTER TABLE quarterly_balance_sheet
    ALTER COLUMN stockholders_equity TYPE NUMERIC(20, 2),
    ALTER COLUMN total_assets TYPE NUMERIC(20, 2),
    ALTER COLUMN total_liabilities TYPE NUMERIC(20, 2);

ALTER TABLE quarterly_income_statement
    ALTER COLUMN revenue TYPE NUMERIC(20, 2),
    ALTER COLUMN net_income TYPE NUMERIC(20, 2);
