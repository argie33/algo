-- Add sample data to fix database API errors

-- Add sample data to annual_balance_sheet for AAPL
INSERT INTO annual_balance_sheet (symbol, fiscal_year, total_assets, current_assets, total_liabilities, current_liabilities, total_equity, retained_earnings, cash_and_equivalents, total_debt, working_capital)
VALUES 
    ('AAPL', 2023, 352755000000, 143566000000, 290437000000, 145308000000, 62318000000, 164038000000, 62639000000, 111109000000, -1742000000),
    ('AAPL', 2022, 352583000000, 135405000000, 302083000000, 153982000000, 50500000000, 148101000000, 48304000000, 120069000000, -18577000000),
    ('MSFT', 2023, 411976000000, 184257000000, 205753000000, 95082000000, 206223000000, 118848000000, 34704000000, 97056000000, 89175000000),
    ('GOOGL', 2023, 402392000000, 154734000000, 115762000000, 45402000000, 286630000000, 286630000000, 110915000000, 28665000000, 109332000000)
ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
    total_assets = EXCLUDED.total_assets,
    current_assets = EXCLUDED.current_assets,
    total_liabilities = EXCLUDED.total_liabilities,
    current_liabilities = EXCLUDED.current_liabilities,
    total_equity = EXCLUDED.total_equity,
    retained_earnings = EXCLUDED.retained_earnings,
    cash_and_equivalents = EXCLUDED.cash_and_equivalents,
    total_debt = EXCLUDED.total_debt,
    working_capital = EXCLUDED.working_capital,
    updated_at = CURRENT_TIMESTAMP;

-- Add sample data to annual_income_statement
INSERT INTO annual_income_statement (symbol, fiscal_year, revenue, cost_of_revenue, gross_profit, operating_expenses, operating_income, net_income, earnings_per_share, shares_outstanding)
VALUES 
    ('AAPL', 2023, 383285000000, 214137000000, 169148000000, 54847000000, 114301000000, 96995000000, 6.16, 15744231000),
    ('AAPL', 2022, 394328000000, 223546000000, 170782000000, 51345000000, 119437000000, 99803000000, 6.11, 16325819000),
    ('MSFT', 2023, 211915000000, 65525000000, 146390000000, 75827000000, 88523000000, 72361000000, 9.65, 7496000000),
    ('GOOGL', 2023, 307394000000, 131836000000, 175558000000, 91742000000, 83816000000, 73795000000, 5.80, 12757000000)
ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    cost_of_revenue = EXCLUDED.cost_of_revenue,
    gross_profit = EXCLUDED.gross_profit,
    operating_expenses = EXCLUDED.operating_expenses,
    operating_income = EXCLUDED.operating_income,
    net_income = EXCLUDED.net_income,
    earnings_per_share = EXCLUDED.earnings_per_share,
    shares_outstanding = EXCLUDED.shares_outstanding,
    updated_at = CURRENT_TIMESTAMP;

-- Add sample portfolio risk data for dev user
INSERT INTO portfolio_risk (portfolio_id, risk_score, beta, var_1d)
VALUES ('dev-user-bypass', 7.5, 1.25, -2.34)
ON CONFLICT (portfolio_id, date) DO UPDATE SET
    risk_score = EXCLUDED.risk_score,
    beta = EXCLUDED.beta,
    var_1d = EXCLUDED.var_1d;

-- Update sentiment scores where they are null
UPDATE stock_scores SET sentiment = 
    CASE 
        WHEN overall_score > 7 THEN ROUND(random() * 20 + 70, 2)  -- Positive sentiment for high scores
        WHEN overall_score > 5 THEN ROUND(random() * 40 + 40, 2)  -- Neutral sentiment for medium scores  
        ELSE ROUND(random() * 40 + 20, 2)  -- Negative sentiment for low scores
    END
WHERE sentiment IS NULL AND overall_score IS NOT NULL;

-- Add some sample market indices data
INSERT INTO market_indices (symbol, name, value, current_price, previous_close, change_percent, change_amount)
VALUES 
    ('SPY', 'SPDR S&P 500 ETF Trust', 560.25, 560.25, 557.80, 0.44, 2.45),
    ('QQQ', 'Invesco QQQ Trust', 495.80, 495.80, 497.05, -0.25, -1.25),
    ('IWM', 'iShares Russell 2000 ETF', 225.40, 225.40, 224.55, 0.38, 0.85),
    ('DIA', 'SPDR Dow Jones Industrial Average ETF', 420.15, 420.15, 416.95, 0.77, 3.20)
ON CONFLICT (symbol, date) DO UPDATE SET
    value = EXCLUDED.value,
    current_price = EXCLUDED.current_price,
    previous_close = EXCLUDED.previous_close,
    change_percent = EXCLUDED.change_percent,
    change_amount = EXCLUDED.change_amount,
    timestamp = CURRENT_TIMESTAMP;

COMMIT;