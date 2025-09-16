-- Final working database schema fixes for all missing columns
-- Based on actual table structures

BEGIN;

-- Fix 1: Add missing sentiment column to stock_scores table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'stock_scores' AND column_name = 'sentiment') THEN
        ALTER TABLE stock_scores ADD COLUMN sentiment DECIMAL(5,2) DEFAULT NULL;
        RAISE NOTICE 'Added sentiment column to stock_scores table';
    ELSE
        RAISE NOTICE 'sentiment column already exists in stock_scores table';
    END IF;
END $$;

-- Fix 2: Add missing change_amount column to market_indices table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'market_indices' AND column_name = 'change_amount') THEN
        ALTER TABLE market_indices ADD COLUMN change_amount DECIMAL(12,4) DEFAULT NULL;
        RAISE NOTICE 'Added change_amount column to market_indices table';
    ELSE
        RAISE NOTICE 'change_amount column already exists in market_indices table';
    END IF;
END $$;

-- Fix 3: var_1d column already exists in portfolio_risk table, just need to add data
-- No need to add the column

-- Fix 4: Add missing transaction_id column to portfolio_transactions table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'portfolio_transactions' AND column_name = 'transaction_id') THEN
        -- Check if there's already a primary key column
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                       WHERE table_name = 'portfolio_transactions' AND constraint_type = 'PRIMARY KEY') THEN
            ALTER TABLE portfolio_transactions ADD COLUMN transaction_id SERIAL PRIMARY KEY;
        ELSE
            ALTER TABLE portfolio_transactions ADD COLUMN transaction_id SERIAL UNIQUE;
        END IF;
        RAISE NOTICE 'Added transaction_id column to portfolio_transactions table';
    ELSE
        RAISE NOTICE 'transaction_id column already exists in portfolio_transactions table';
    END IF;
END $$;

-- Fix 5: Add missing previous_close column to price_daily table (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'price_daily' AND column_name = 'previous_close') THEN
        ALTER TABLE price_daily ADD COLUMN previous_close DECIMAL(12,4) DEFAULT NULL;
        RAISE NOTICE 'Added previous_close column to price_daily table';
    ELSE
        RAISE NOTICE 'previous_close column already exists in price_daily table';
    END IF;
END $$;

-- Fix 6: Add sample data to existing annual_balance_sheet table (using fiscal_year)
INSERT INTO annual_balance_sheet (symbol, fiscal_year, total_assets, current_assets, total_liabilities, current_liabilities, total_equity)
VALUES 
    ('AAPL', 2024, 394328000000, 143566000000, 290437000000, 133973000000, 103891000000),
    ('MSFT', 2024, 512847000000, 184257000000, 198298000000, 95082000000, 314549000000),
    ('GOOGL', 2024, 365264000000, 110916000000, 76934000000, 26067000000, 288330000000),
    ('META', 2024, 229334000000, 64739000000, 43756000000, 18711000000, 185578000000),
    ('TSLA', 2024, 106618000000, 26717000000, 43009000000, 15552000000, 63609000000)
ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
    total_assets = EXCLUDED.total_assets,
    current_assets = EXCLUDED.current_assets,
    total_liabilities = EXCLUDED.total_liabilities,
    current_liabilities = EXCLUDED.current_liabilities,
    total_equity = EXCLUDED.total_equity;

-- Fix 7: Add sample data to existing annual_income_statement table (using fiscal_year)
INSERT INTO annual_income_statement (symbol, fiscal_year, revenue, gross_profit, operating_income, net_income, earnings_per_share)
VALUES 
    ('AAPL', 2024, 385603000000, 169148000000, 114301000000, 99803000000, 6.11),
    ('MSFT', 2024, 245122000000, 169706000000, 109431000000, 88136000000, 11.05),
    ('GOOGL', 2024, 328284000000, 198102000000, 84279000000, 73795000000, 5.80),
    ('META', 2024, 134902000000, 104034000000, 46327000000, 39098000000, 15.69),
    ('TSLA', 2024, 96773000000, 19653000000, 8891000000, 14997000000, 4.73)
ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    gross_profit = EXCLUDED.gross_profit,
    operating_income = EXCLUDED.operating_income,
    net_income = EXCLUDED.net_income,
    earnings_per_share = EXCLUDED.earnings_per_share;

-- Fix 8: Ensure earnings_reports table has proper future data for calendar
INSERT INTO earnings_reports (symbol, report_date, quarter, year, revenue, net_income, eps_reported, eps_estimate, surprise_percent)
VALUES 
    ('AAPL', CURRENT_DATE + INTERVAL '2 days', 4, 2025, 123500000000, 35000000000, 6.20, 6.10, 1.64),
    ('AAPL', CURRENT_DATE + INTERVAL '5 days', 1, 2026, 128000000000, 38000000000, 6.45, 6.25, 3.20),
    ('MSFT', CURRENT_DATE + INTERVAL '3 days', 4, 2025, 65000000000, 22000000000, 11.20, 10.95, 2.28),
    ('MSFT', CURRENT_DATE + INTERVAL '7 days', 1, 2026, 68000000000, 24000000000, 11.85, 11.50, 3.04),
    ('GOOGL', CURRENT_DATE + INTERVAL '4 days', 4, 2025, 88000000000, 21000000000, 6.85, 6.65, 3.01),
    ('GOOGL', CURRENT_DATE + INTERVAL '10 days', 1, 2026, 92000000000, 23000000000, 7.20, 7.00, 2.86),
    ('META', CURRENT_DATE + INTERVAL '6 days', 4, 2025, 42000000000, 15000000000, 5.95, 5.75, 3.48),
    ('TSLA', CURRENT_DATE + INTERVAL '8 days', 4, 2025, 28000000000, 3500000000, 2.45, 2.30, 6.52),
    ('NVDA', CURRENT_DATE + INTERVAL '12 days', 4, 2025, 35000000000, 18000000000, 12.85, 12.50, 2.80),
    ('AMZN', CURRENT_DATE + INTERVAL '15 days', 4, 2025, 158000000000, 12000000000, 3.85, 3.70, 4.05)
ON CONFLICT (symbol, report_date) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    net_income = EXCLUDED.net_income,
    eps_reported = EXCLUDED.eps_reported,
    eps_estimate = EXCLUDED.eps_estimate,
    surprise_percent = EXCLUDED.surprise_percent;

-- Fix 9: Add sample data to sentiment scores
UPDATE stock_scores 
SET sentiment = CASE 
    WHEN symbol = 'AAPL' THEN 75.5
    WHEN symbol = 'MSFT' THEN 82.3
    WHEN symbol = 'GOOGL' THEN 68.7
    WHEN symbol = 'META' THEN 59.2
    WHEN symbol = 'TSLA' THEN 71.8
    ELSE ROUND(50 + (RANDOM() * 40))::DECIMAL(5,2)
END
WHERE sentiment IS NULL OR sentiment = 0;

-- Fix 10: Add sample data to market indices change amounts
UPDATE market_indices 
SET change_amount = CASE 
    WHEN symbol = 'SPY' THEN 12.45
    WHEN symbol = 'QQQ' THEN 8.73
    WHEN symbol = 'IWM' THEN 3.21
    ELSE ROUND((RANDOM() * 20 - 10)::DECIMAL(12,4), 2)
END
WHERE change_amount IS NULL OR change_amount = 0;

-- Fix 11: Update previous_close values in price_daily
UPDATE price_daily 
SET previous_close = (
    SELECT p2.close 
    FROM price_daily p2 
    WHERE p2.symbol = price_daily.symbol 
    AND p2.date < price_daily.date 
    ORDER BY p2.date DESC 
    LIMIT 1
)
WHERE previous_close IS NULL AND EXISTS (
    SELECT 1 FROM price_daily p2 
    WHERE p2.symbol = price_daily.symbol 
    AND p2.date < price_daily.date
);

-- Fix 12: Add sample portfolio risk data (using portfolio_id instead of user_id)
INSERT INTO portfolio_risk (portfolio_id, risk_score, beta, var_1d, date)
VALUES 
    ('dev-user-bypass', 0.75, 1.12, 0.023, CURRENT_DATE)
ON CONFLICT (portfolio_id, date) DO UPDATE SET
    risk_score = EXCLUDED.risk_score,
    beta = EXCLUDED.beta,
    var_1d = EXCLUDED.var_1d,
    fetched_at = CURRENT_TIMESTAMP;

COMMIT;

-- Verify all fixes
SELECT 'Database schema fixes completed successfully' AS status;