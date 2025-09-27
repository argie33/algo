-- Create comprehensive key_metrics table matching yfinance data structure
-- This table stores all the key financial metrics that yfinance provides

CREATE TABLE IF NOT EXISTS key_metrics (
    symbol VARCHAR(10) NOT NULL,
    date_updated DATE DEFAULT CURRENT_DATE,

    -- Price-related metrics
    current_price DECIMAL(15,4),
    open_price DECIMAL(15,4),

    -- PE ratios
    trailing_pe DECIMAL(10,4),
    forward_pe DECIMAL(10,4),
    price_eps_current_year DECIMAL(10,4),
    trailing_peg_ratio DECIMAL(10,4),

    -- Book value and price ratios
    book_value DECIMAL(10,4),
    price_to_book DECIMAL(10,4),
    price_to_sales_trailing_12m DECIMAL(10,4),

    -- Enterprise value metrics
    enterprise_value BIGINT,
    enterprise_to_revenue DECIMAL(10,4),
    enterprise_to_ebitda DECIMAL(10,4),

    -- Profitability margins
    profit_margins DECIMAL(8,6),
    gross_margins DECIMAL(8,6),
    ebitda_margins DECIMAL(8,6),
    operating_margins DECIMAL(8,6),

    -- EPS metrics
    trailing_eps DECIMAL(10,4),
    forward_eps DECIMAL(10,4),
    eps_current_year DECIMAL(10,4),

    -- Returns
    return_on_assets DECIMAL(8,6),
    return_on_equity DECIMAL(8,6),

    -- Liquidity ratios
    current_ratio DECIMAL(8,4),
    quick_ratio DECIMAL(8,4),

    -- Debt metrics
    total_debt BIGINT,
    debt_to_equity DECIMAL(10,4),

    -- Cash metrics
    total_cash_per_share DECIMAL(10,4),
    operating_cashflow BIGINT,

    -- Share metrics
    shares_outstanding BIGINT,
    float_shares BIGINT,
    shares_short BIGINT,
    shares_short_prior_month BIGINT,
    shares_percent_shares_out DECIMAL(8,6),
    short_ratio DECIMAL(8,4),
    short_percent_of_float DECIMAL(8,6),

    -- Insider and institutional holdings
    held_percent_insiders DECIMAL(8,6),
    held_percent_institutions DECIMAL(8,6),

    -- Revenue metrics
    revenue_per_share DECIMAL(10,4),

    -- EBITDA
    ebitda BIGINT,

    -- Dividend metrics
    trailing_annual_dividend_rate DECIMAL(10,4),
    trailing_annual_dividend_yield DECIMAL(8,6),
    payout_ratio DECIMAL(8,6),

    -- Change percentages
    regular_market_change_percent DECIMAL(8,6),
    fifty_day_average_change_percent DECIMAL(8,6),
    two_hundred_day_average_change_percent DECIMAL(8,6),
    fifty_two_week_low_change_percent DECIMAL(8,6),
    fifty_two_week_high_change_percent DECIMAL(8,6),
    fifty_two_week_change_percent DECIMAL(8,6),

    -- Timestamps
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (symbol, date_updated)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_key_metrics_symbol ON key_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_key_metrics_updated ON key_metrics(last_updated);
CREATE INDEX IF NOT EXISTS idx_key_metrics_pe ON key_metrics(trailing_pe);
CREATE INDEX IF NOT EXISTS idx_key_metrics_pb ON key_metrics(price_to_book);
CREATE INDEX IF NOT EXISTS idx_key_metrics_roe ON key_metrics(return_on_equity);

-- Grant permissions
GRANT ALL PRIVILEGES ON key_metrics TO stocks;