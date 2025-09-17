-- Fix Database Schema - Add Missing Columns
-- This script adds all missing columns identified from test failures

-- Fix user_portfolio table
ALTER TABLE user_portfolio
ADD COLUMN IF NOT EXISTS cost_basis DECIMAL(15,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_value DECIMAL(15,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Fix trade_history table
ALTER TABLE trade_history
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'completed',
ADD COLUMN IF NOT EXISTS side VARCHAR(10) DEFAULT 'buy',
ADD COLUMN IF NOT EXISTS date TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Fix portfolio_holdings table
ALTER TABLE portfolio_holdings
ADD COLUMN IF NOT EXISTS avg_exit_price DECIMAL(15,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_value DECIMAL(15,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Fix user_risk_limits table
ALTER TABLE user_risk_limits
ADD COLUMN IF NOT EXISTS stop_loss_percentage DECIMAL(5,2) DEFAULT 0;

-- Create position_history table if it doesn't exist
CREATE TABLE IF NOT EXISTS position_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    avg_exit_price DECIMAL(15,4) DEFAULT 0,
    quantity INTEGER DEFAULT 0,
    side VARCHAR(10) DEFAULT 'buy',
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create trade_executions table if it doesn't exist
CREATE TABLE IF NOT EXISTS trade_executions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    commission DECIMAL(10,4) DEFAULT 0,
    side VARCHAR(10) DEFAULT 'buy',
    quantity INTEGER DEFAULT 0,
    price DECIMAL(15,4) DEFAULT 0,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create watchlist table if it doesn't exist
CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Add missing columns to existing tables for financial data
DO \$\$
BEGIN
    -- Add debt_to_equity column to financials tables
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'company_financials') THEN
        ALTER TABLE company_financials
        ADD COLUMN IF NOT EXISTS debt_to_equity DECIMAL(10,4) DEFAULT 0;
    END IF;

    -- Add volatility columns to price tables
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'price_daily') THEN
        ALTER TABLE price_daily
        ADD COLUMN IF NOT EXISTS volatility_30d DECIMAL(10,6) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS percentage_change DECIMAL(10,4) DEFAULT 0;
    END IF;

    -- Add date column to tables that need it
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'balance_sheet') THEN
        ALTER TABLE balance_sheet
        ADD COLUMN IF NOT EXISTS date DATE DEFAULT CURRENT_DATE;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'income_statement') THEN
        ALTER TABLE income_statement
        ADD COLUMN IF NOT EXISTS date DATE DEFAULT CURRENT_DATE;
    END IF;
END
\$\$;

COMMIT;
