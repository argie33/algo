-- Migration 1303: Extend xbrl_yfinance_line_item_report to also hold quarterly comparisons.
--
-- 2026-09-17 follow-up to the divergence-repair incident work: scripts/xbrl_yfinance_crosscheck.py
-- (and this table, migration 1300) only ever covered annual_income_statement/annual_balance_sheet/
-- annual_cash_flow. quarterly_income_statement/quarterly_balance_sheet/quarterly_cash_flow are
-- populated tables with zero automated cross-check coverage against yfinance - a real, previously
-- undiscovered blind spot distinct from the original corruption incident.
--
-- Extends the EXISTING table/tooling rather than creating a sibling, so scripts/
-- xbrl_line_item_report.py (read side) and scripts/xbrl_line_item_review.py (review-marking side)
-- work for both periods without duplicate tooling. fiscal_quarter is NOT NULL DEFAULT 0, where 0
-- means "this is an annual row" - deliberately not NULL, because Postgres treats NULL as distinct
-- for UNIQUE-constraint purposes, which would silently break the ON CONFLICT upsert this table
-- depends on for idempotent re-runs (multiple "NULL fiscal_quarter" rows for the same
-- symbol/table/field/fiscal_year would not conflict with each other and would never upsert).
-- Every existing annual row backfills to fiscal_quarter=0 for free via the column default,
-- and the widened UNIQUE constraint is byte-for-byte equivalent to the old one for that subset
-- (fiscal_quarter is constant 0 across all of them), so this is a no-op for existing annual data
-- and callers that never pass fiscal_quarter.

ALTER TABLE xbrl_yfinance_line_item_report
    ADD COLUMN IF NOT EXISTS fiscal_quarter SMALLINT NOT NULL DEFAULT 0 CHECK (fiscal_quarter BETWEEN 0 AND 4),
    ADD COLUMN IF NOT EXISTS period_type VARCHAR(10) NOT NULL DEFAULT 'annual'
        CHECK (period_type IN ('annual', 'quarterly'));

-- Keep period_type consistent with fiscal_quarter rather than trusting two independently-set
-- values to agree - a CHECK, not application-level discipline alone.
ALTER TABLE xbrl_yfinance_line_item_report
    ADD CONSTRAINT xbrl_yf_line_item_period_type_matches_quarter
        CHECK ((fiscal_quarter = 0 AND period_type = 'annual') OR (fiscal_quarter BETWEEN 1 AND 4 AND period_type = 'quarterly'));

ALTER TABLE xbrl_yfinance_line_item_report
    DROP CONSTRAINT IF EXISTS xbrl_yfinance_line_item_repor_symbol_our_table_our_field_fi_key;
ALTER TABLE xbrl_yfinance_line_item_report
    ADD CONSTRAINT xbrl_yf_line_item_report_identity_key
        UNIQUE (symbol, our_table, our_field, fiscal_year, fiscal_quarter);

CREATE INDEX IF NOT EXISTS idx_xbrl_yf_line_item_period_type
    ON xbrl_yfinance_line_item_report(period_type);

COMMENT ON COLUMN xbrl_yfinance_line_item_report.fiscal_quarter IS
    '0 = annual row (our_table is one of the annual_* tables). 1-4 = quarterly row '
    '(our_table is one of the quarterly_* tables), matched against yfinance''s quarterly period '
    'by CALENDAR quarter of period-end month, not the filer''s own fiscal-quarter numbering - '
    'same approximation the annual comparison already accepts for calendar-year matching on '
    'non-calendar-fiscal-year filers (see utils/external/yfinance_financials.py''s '
    '_build_period_row docstring). A real, accepted precision limit, not a bug.';
