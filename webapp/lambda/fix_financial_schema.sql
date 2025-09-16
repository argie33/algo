-- Fix Financial Database Schema Issues
-- This script creates the financial tables with the CORRECT schema from Python loaders

-- Drop and recreate tables to ensure correct schema
DROP TABLE IF EXISTS annual_balance_sheet CASCADE;
DROP TABLE IF EXISTS annual_income_statement CASCADE;
DROP TABLE IF EXISTS annual_cash_flow CASCADE;
DROP TABLE IF EXISTS quarterly_balance_sheet CASCADE;
DROP TABLE IF EXISTS quarterly_income_statement CASCADE;
DROP TABLE IF EXISTS quarterly_cash_flow CASCADE;

-- Create annual_balance_sheet table (from loadannualbalancesheet.py schema)
CREATE TABLE annual_balance_sheet (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

-- Create annual_income_statement table (from loadannualincomestatement.py schema)
CREATE TABLE annual_income_statement (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

-- Create annual_cash_flow table (from loadannualcashflow.py schema)
CREATE TABLE annual_cash_flow (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

-- Create quarterly_balance_sheet table (from loadquarterlybalancesheet.py schema)
CREATE TABLE quarterly_balance_sheet (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

-- Create quarterly_income_statement table (from loadquarterlyincomestatement.py schema)
CREATE TABLE quarterly_income_statement (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

-- Create quarterly_cash_flow table (from loadquarterlycashflow.py schema)
CREATE TABLE quarterly_cash_flow (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

-- Create indexes for performance
CREATE INDEX idx_annual_balance_sheet_symbol ON annual_balance_sheet(symbol);
CREATE INDEX idx_annual_balance_sheet_date ON annual_balance_sheet(date);
CREATE INDEX idx_annual_income_statement_symbol ON annual_income_statement(symbol);
CREATE INDEX idx_annual_income_statement_date ON annual_income_statement(date);
CREATE INDEX idx_annual_cash_flow_symbol ON annual_cash_flow(symbol);
CREATE INDEX idx_annual_cash_flow_date ON annual_cash_flow(date);
CREATE INDEX idx_quarterly_balance_sheet_symbol ON quarterly_balance_sheet(symbol);
CREATE INDEX idx_quarterly_balance_sheet_date ON quarterly_balance_sheet(date);
CREATE INDEX idx_quarterly_income_statement_symbol ON quarterly_income_statement(symbol);
CREATE INDEX idx_quarterly_income_statement_date ON quarterly_income_statement(date);
CREATE INDEX idx_quarterly_cash_flow_symbol ON quarterly_cash_flow(symbol);
CREATE INDEX idx_quarterly_cash_flow_date ON quarterly_cash_flow(date);

-- Add sample data for testing (AAPL)
INSERT INTO annual_balance_sheet (symbol, date, item_name, value) VALUES
('AAPL', '2023-12-31', 'Total Assets', 352755000000),
('AAPL', '2023-12-31', 'Current Assets', 143566000000),
('AAPL', '2023-12-31', 'Cash And Cash Equivalents', 29965000000),
('AAPL', '2023-12-31', 'Total Liabilities', 279437000000),
('AAPL', '2023-12-31', 'Current Liabilities', 133973000000),
('AAPL', '2023-12-31', 'Total Equity', 73318000000),
('AAPL', '2022-12-31', 'Total Assets', 352893000000),
('AAPL', '2022-12-31', 'Current Assets', 135405000000),
('AAPL', '2022-12-31', 'Cash And Cash Equivalents', 23646000000),
('AAPL', '2022-12-31', 'Total Liabilities', 302083000000),
('AAPL', '2022-12-31', 'Current Liabilities', 153982000000),
('AAPL', '2022-12-31', 'Total Equity', 50810000000);

INSERT INTO annual_income_statement (symbol, date, item_name, value) VALUES
('AAPL', '2023-12-31', 'Total Revenue', 383285000000),
('AAPL', '2023-12-31', 'Gross Profit', 169148000000),
('AAPL', '2023-12-31', 'Operating Income', 114301000000),
('AAPL', '2023-12-31', 'Net Income', 97019000000),
('AAPL', '2023-12-31', 'Basic EPS', 6.16),
('AAPL', '2022-12-31', 'Total Revenue', 394328000000),
('AAPL', '2022-12-31', 'Gross Profit', 170782000000),
('AAPL', '2022-12-31', 'Operating Income', 119437000000),
('AAPL', '2022-12-31', 'Net Income', 99803000000),
('AAPL', '2022-12-31', 'Basic EPS', 6.15);

INSERT INTO annual_cash_flow (symbol, date, item_name, value) VALUES
('AAPL', '2023-12-31', 'Operating Cash Flow', 110563000000),
('AAPL', '2023-12-31', 'Capital Expenditures', -10959000000),
('AAPL', '2023-12-31', 'Free Cash Flow', 99604000000),
('AAPL', '2023-12-31', 'Dividends Paid', -15025000000),
('AAPL', '2022-12-31', 'Operating Cash Flow', 122151000000),
('AAPL', '2022-12-31', 'Capital Expenditures', -11085000000),
('AAPL', '2022-12-31', 'Free Cash Flow', 111066000000),
('AAPL', '2022-12-31', 'Dividends Paid', -14841000000);

-- Add some quarterly data as well for testing
INSERT INTO quarterly_income_statement (symbol, date, item_name, value) VALUES
('AAPL', '2024-03-31', 'Total Revenue', 90753000000),
('AAPL', '2024-03-31', 'Gross Profit', 41862000000),
('AAPL', '2024-03-31', 'Operating Income', 27421000000),
('AAPL', '2024-03-31', 'Net Income', 23636000000),
('AAPL', '2023-12-31', 'Total Revenue', 119575000000),
('AAPL', '2023-12-31', 'Gross Profit', 54731000000),
('AAPL', '2023-12-31', 'Operating Income', 40323000000),
('AAPL', '2023-12-31', 'Net Income', 33916000000);

COMMIT;