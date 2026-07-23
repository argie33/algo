-- Migration 120: Add enterprise value and EBITDA-based metrics to sec_valuations
-- Enables EV/EBITDA and EV/Revenue valuation ratios

BEGIN;

-- Add enterprise value metrics columns
ALTER TABLE sec_valuations
ADD COLUMN IF NOT EXISTS total_debt NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS total_cash NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS enterprise_value NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS ebitda NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS ev_ebitda NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS ev_revenue NUMERIC(10, 2);

-- Add column for forward P/E (may need yfinance earnings estimates)
ALTER TABLE sec_valuations
ADD COLUMN IF NOT EXISTS forward_pe NUMERIC(10, 2);

COMMIT;
