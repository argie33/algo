-- Fix dividend_calendar table schema mismatch
-- The route expects: ex_dividend_date, payment_date, dividend_yield, announcement_date
-- But database.js creates: ex_date, pay_date, yield_percent

-- Add missing columns to dividend_calendar
ALTER TABLE dividend_calendar 
ADD COLUMN IF NOT EXISTS ex_dividend_date DATE,
ADD COLUMN IF NOT EXISTS payment_date DATE,
ADD COLUMN IF NOT EXISTS dividend_yield DECIMAL(10,4),
ADD COLUMN IF NOT EXISTS announcement_date DATE;

-- Update existing data to match expected column names
UPDATE dividend_calendar SET ex_dividend_date = ex_date WHERE ex_dividend_date IS NULL AND ex_date IS NOT NULL;
UPDATE dividend_calendar SET payment_date = pay_date WHERE payment_date IS NULL AND pay_date IS NOT NULL;
UPDATE dividend_calendar SET dividend_yield = yield_percent WHERE dividend_yield IS NULL AND yield_percent IS NOT NULL;

-- Create the annual_balance_sheet table with the correct schema
-- The route expects: symbol, date, item_name, value
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- Add sample data for AAPL balance sheet
INSERT INTO annual_balance_sheet (symbol, date, item_name, value)
VALUES 
    ('AAPL', '2024-09-30', 'Total Assets', 394328000000),
    ('AAPL', '2024-09-30', 'Current Assets', 143566000000),
    ('AAPL', '2024-09-30', 'Total Liabilities', 290437000000),
    ('AAPL', '2024-09-30', 'Current Liabilities', 133973000000),
    ('AAPL', '2024-09-30', 'Total Equity', 103891000000),
    ('AAPL', '2024-09-30', 'Retained Earnings', 84162000000),
    ('AAPL', '2023-09-30', 'Total Assets', 352755000000),
    ('AAPL', '2023-09-30', 'Current Assets', 143566000000),
    ('AAPL', '2023-09-30', 'Total Liabilities', 290437000000),
    ('AAPL', '2023-09-30', 'Current Liabilities', 145308000000),
    ('AAPL', '2023-09-30', 'Total Equity', 62318000000),
    ('AAPL', '2023-09-30', 'Retained Earnings', 148101000000)
ON CONFLICT (symbol, date, item_name) DO NOTHING;

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol_date ON annual_balance_sheet(symbol, date);