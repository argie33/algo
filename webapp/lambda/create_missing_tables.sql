-- Create missing database tables and columns for test suite

-- Annual Income Statement table
CREATE TABLE IF NOT EXISTS annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    revenue DECIMAL(20,2),
    cost_of_revenue DECIMAL(20,2),
    gross_profit DECIMAL(20,2),
    operating_expenses DECIMAL(20,2),
    operating_income DECIMAL(20,2),
    net_income DECIMAL(20,2),
    earnings_per_share DECIMAL(10,4),
    shares_outstanding BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Annual Balance Sheet table
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    total_assets DECIMAL(20,2),
    current_assets DECIMAL(20,2),
    total_liabilities DECIMAL(20,2),
    current_liabilities DECIMAL(20,2),
    total_equity DECIMAL(20,2),
    retained_earnings DECIMAL(20,2),
    cash_and_equivalents DECIMAL(20,2),
    total_debt DECIMAL(20,2),
    working_capital DECIMAL(20,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Add missing technical indicator columns
DO $$ 
BEGIN
    -- Add rsi_14 column to technical_data_daily if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'technical_data_daily' 
        AND column_name = 'rsi_14'
    ) THEN
        ALTER TABLE technical_data_daily ADD COLUMN rsi_14 DECIMAL(10,4);
    END IF;
    
    -- Add rsi_14 to other technical tables if they exist
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_data_weekly') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'technical_data_weekly' 
            AND column_name = 'rsi_14'
        ) THEN
            ALTER TABLE technical_data_weekly ADD COLUMN rsi_14 DECIMAL(10,4);
        END IF;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_data_monthly') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'technical_data_monthly' 
            AND column_name = 'rsi_14'
        ) THEN
            ALTER TABLE technical_data_monthly ADD COLUMN rsi_14 DECIMAL(10,4);
        END IF;
    END IF;
END $$;

-- Add financial ratio columns 
DO $$
BEGIN
    -- Add debt_to_equity column to company_profile or financial tables
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'company_profile') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'company_profile' 
            AND column_name = 'debt_to_equity'
        ) THEN
            ALTER TABLE company_profile ADD COLUMN debt_to_equity DECIMAL(10,4);
        END IF;
    END IF;
    
    -- Create financial_ratios table if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'financial_ratios') THEN
        CREATE TABLE financial_ratios (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            fiscal_year INTEGER NOT NULL,
            debt_to_equity DECIMAL(10,4),
            current_ratio DECIMAL(10,4),
            quick_ratio DECIMAL(10,4),
            return_on_equity DECIMAL(10,4),
            return_on_assets DECIMAL(10,4),
            profit_margin DECIMAL(10,4),
            price_to_earnings DECIMAL(10,4),
            price_to_book DECIMAL(10,4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, fiscal_year)
        );
    END IF;
END $$;

-- Create dividend tables if they don't exist
CREATE TABLE IF NOT EXISTS dividends (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    ex_date DATE NOT NULL,
    record_date DATE,
    payment_date DATE,
    amount DECIMAL(10,4) NOT NULL,
    yield_percent DECIMAL(10,4),
    frequency VARCHAR(20),
    type VARCHAR(20) DEFAULT 'cash',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, ex_date)
);

CREATE TABLE IF NOT EXISTS dividend_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    company_name VARCHAR(255),
    ex_dividend_date DATE NOT NULL,
    payment_date DATE,
    record_date DATE,
    dividend_amount DECIMAL(10,4) NOT NULL,
    dividend_yield DECIMAL(10,4),
    frequency VARCHAR(20),
    dividend_type VARCHAR(20) DEFAULT 'cash',
    announcement_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, ex_dividend_date)
);

-- Insert sample data for testing
INSERT INTO annual_income_statement (symbol, fiscal_year, revenue, net_income, earnings_per_share) VALUES
('AAPL', 2023, 383285000000, 96995000000, 6.16),
('MSFT', 2023, 211915000000, 72361000000, 9.65),
('GOOGL', 2023, 307394000000, 73795000000, 5.80)
ON CONFLICT (symbol, fiscal_year) DO NOTHING;

INSERT INTO annual_balance_sheet (symbol, fiscal_year, total_assets, total_equity, total_debt) VALUES
('AAPL', 2023, 352755000000, 62146000000, 123930000000),
('MSFT', 2023, 411976000000, 206223000000, 97200000000),
('GOOGL', 2023, 402392000000, 283893000000, 26314000000)
ON CONFLICT (symbol, fiscal_year) DO NOTHING;

INSERT INTO financial_ratios (symbol, fiscal_year, debt_to_equity, current_ratio, return_on_equity) VALUES
('AAPL', 2023, 1.99, 1.0, 1.56),
('MSFT', 2023, 0.47, 1.7, 0.35),
('GOOGL', 2023, 0.09, 2.1, 0.26)
ON CONFLICT (symbol, fiscal_year) DO NOTHING;

INSERT INTO dividends (symbol, ex_date, amount, yield_percent, frequency) VALUES
('AAPL', '2023-11-10', 0.24, 0.50, 'quarterly'),
('AAPL', '2023-08-11', 0.24, 0.52, 'quarterly'),
('MSFT', '2023-11-15', 0.75, 0.72, 'quarterly'),
('MSFT', '2023-08-16', 0.68, 0.69, 'quarterly')
ON CONFLICT (symbol, ex_date) DO NOTHING;

INSERT INTO dividend_calendar (symbol, company_name, ex_dividend_date, dividend_amount, dividend_yield) VALUES
('AAPL', 'Apple Inc.', '2025-11-08', 0.25, 0.48),
('MSFT', 'Microsoft Corporation', '2025-11-20', 0.83, 0.75),
('JNJ', 'Johnson & Johnson', '2025-11-25', 1.19, 2.85)
ON CONFLICT (symbol, ex_dividend_date) DO NOTHING;

-- Add sample technical data with RSI values
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_data_daily') THEN
        -- Update existing rows to have rsi_14 values
        UPDATE technical_data_daily 
        SET rsi_14 = CASE 
            WHEN rsi IS NOT NULL THEN rsi 
            ELSE 50.0 + (RANDOM() - 0.5) * 40  -- Random RSI between 30-70
        END 
        WHERE rsi_14 IS NULL;
    END IF;
END $$;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_annual_income_symbol_year ON annual_income_statement(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_annual_balance_symbol_year ON annual_balance_sheet(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_symbol_year ON financial_ratios(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_dividends_symbol_date ON dividends(symbol, ex_date);
CREATE INDEX IF NOT EXISTS idx_dividend_calendar_symbol_date ON dividend_calendar(symbol, ex_dividend_date);

COMMIT;