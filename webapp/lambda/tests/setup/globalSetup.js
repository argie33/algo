// Global setup for tests - ensures database tables match loader structure
module.exports = async () => {
  process.env.NODE_ENV = "test";

  // Set database environment variables BEFORE importing database module
  process.env.DB_HOST = "localhost";
  process.env.DB_USER = "postgres";
  process.env.DB_PASSWORD = "password";
  process.env.DB_NAME = "stocks";
  process.env.DB_PORT = "5432";
  process.env.DB_SSL = "false";

  try {
    const { query } = require('../../utils/database');

    console.log('🔧 Setting up database tables to match loader structure...');

    // Create company_profile table (from loadinfo.py)
    await query(`
      CREATE TABLE IF NOT EXISTS company_profile (
        ticker VARCHAR(10) PRIMARY KEY,
        short_name VARCHAR(100),
        long_name VARCHAR(200),
        sector VARCHAR(100),
        industry VARCHAR(100),
        currency VARCHAR(10),
        exchange VARCHAR(50),
        website VARCHAR(255),
        business_summary TEXT,
        full_time_employees INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Recreate buy_sell_daily table with correct schema
    await query(`DROP TABLE IF EXISTS buy_sell_daily`);
    await query(`
      CREATE TABLE buy_sell_daily (
        symbol VARCHAR(20) NOT NULL,
        date DATE NOT NULL,
        timeframe VARCHAR(10) NOT NULL DEFAULT 'daily',
        signal_type VARCHAR(10) NOT NULL,
        confidence DECIMAL(5,2) NOT NULL DEFAULT 0.0,
        price DECIMAL(12,4),
        rsi DECIMAL(5,2),
        macd DECIMAL(10,6),
        volume BIGINT,
        volume_avg_10d BIGINT,
        price_vs_ma20 DECIMAL(5,2),
        price_vs_ma50 DECIMAL(5,2),
        bollinger_position DECIMAL(5,2),
        support_level DECIMAL(12,4),
        resistance_level DECIMAL(12,4),
        pattern_score DECIMAL(5,2),
        momentum_score DECIMAL(5,2),
        risk_score DECIMAL(5,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        buylevel REAL,
        stoplevel REAL,
        inposition BOOLEAN,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        PRIMARY KEY (symbol, date, timeframe, signal_type)
      )
    `);

    // Recreate earnings_history table with correct schema
    await query(`DROP TABLE IF EXISTS earnings_history`);
    await query(`
      CREATE TABLE earnings_history (
        symbol VARCHAR(20) NOT NULL,
        quarter DATE NOT NULL,
        eps_actual NUMERIC,
        eps_estimate NUMERIC,
        eps_difference NUMERIC,
        surprise_percent NUMERIC,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, quarter)
      )
    `);

    // Create earnings_estimates table (from loadearningsestimate.py)
    await query(`
      CREATE TABLE IF NOT EXISTS earnings_estimates (
        symbol VARCHAR(20) NOT NULL,
        period VARCHAR(3) NOT NULL,
        avg_estimate NUMERIC,
        low_estimate NUMERIC,
        high_estimate NUMERIC,
        year_ago_eps NUMERIC,
        number_of_analysts INTEGER,
        growth NUMERIC,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, period)
      )
    `);

    // Create earnings_metrics table (from loadearningsmetrics.py)
    await query(`
      CREATE TABLE IF NOT EXISTS earnings_metrics (
        symbol VARCHAR(50),
        report_date DATE,
        eps_growth_1q DOUBLE PRECISION,
        eps_growth_2q DOUBLE PRECISION,
        eps_growth_4q DOUBLE PRECISION,
        eps_growth_8q DOUBLE PRECISION,
        eps_acceleration_qtrs DOUBLE PRECISION,
        eps_surprise_last_q DOUBLE PRECISION,
        eps_estimate_revision_1m DOUBLE PRECISION,
        eps_estimate_revision_3m DOUBLE PRECISION,
        eps_estimate_revision_6m DOUBLE PRECISION,
        annual_eps_growth_1y DOUBLE PRECISION,
        annual_eps_growth_3y DOUBLE PRECISION,
        annual_eps_growth_5y DOUBLE PRECISION,
        consecutive_eps_growth_years INTEGER,
        eps_estimated_change_this_year DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, report_date)
      )
    `);

    // Create analyst_upgrade_downgrade table (from loadanalystupgradedowngrade.py)
    await query(`
      CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        firm VARCHAR(128),
        action VARCHAR(32),
        from_grade VARCHAR(64),
        to_grade VARCHAR(64),
        date DATE NOT NULL,
        details TEXT,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create buy_sell_weekly table
    await query(`
      CREATE TABLE IF NOT EXISTS buy_sell_weekly (
        symbol VARCHAR(20) NOT NULL,
        date DATE NOT NULL,
        timeframe VARCHAR(10) NOT NULL DEFAULT 'weekly',
        signal_type VARCHAR(10) NOT NULL,
        confidence DECIMAL(5,2) NOT NULL DEFAULT 0.0,
        price DECIMAL(12,4),
        rsi DECIMAL(5,2),
        macd DECIMAL(10,6),
        volume BIGINT,
        volume_avg_10d BIGINT,
        price_vs_ma20 DECIMAL(5,2),
        price_vs_ma50 DECIMAL(5,2),
        bollinger_position DECIMAL(5,2),
        support_level DECIMAL(12,4),
        resistance_level DECIMAL(12,4),
        pattern_score DECIMAL(5,2),
        momentum_score DECIMAL(5,2),
        risk_score DECIMAL(5,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date, timeframe, signal_type)
      )
    `);

    // Create buy_sell_monthly table
    await query(`
      CREATE TABLE IF NOT EXISTS buy_sell_monthly (
        symbol VARCHAR(20) NOT NULL,
        date DATE NOT NULL,
        timeframe VARCHAR(10) NOT NULL DEFAULT 'monthly',
        signal_type VARCHAR(10) NOT NULL,
        confidence DECIMAL(5,2) NOT NULL DEFAULT 0.0,
        price DECIMAL(12,4),
        rsi DECIMAL(5,2),
        macd DECIMAL(10,6),
        volume BIGINT,
        volume_avg_10d BIGINT,
        price_vs_ma20 DECIMAL(5,2),
        price_vs_ma50 DECIMAL(5,2),
        bollinger_position DECIMAL(5,2),
        support_level DECIMAL(12,4),
        resistance_level DECIMAL(12,4),
        pattern_score DECIMAL(5,2),
        momentum_score DECIMAL(5,2),
        risk_score DECIMAL(5,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date, timeframe, signal_type)
      )
    `);

    // Create other essential tables that tests expect
    await query(`
      CREATE TABLE IF NOT EXISTS stock_symbols (
        symbol VARCHAR(50),
        exchange VARCHAR(100),
        security_name TEXT,
        cqs_symbol VARCHAR(50),
        market_category VARCHAR(50),
        test_issue CHAR(1),
        financial_status VARCHAR(50),
        round_lot_size INT,
        etf CHAR(1),
        secondary_symbol VARCHAR(50)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS market_data (
        ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
        market_cap BIGINT,
        current_price DECIMAL(12,4),
        previous_close DECIMAL(12,4),
        volume BIGINT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`DROP TABLE IF EXISTS price_daily`);
    await query(`
      CREATE TABLE price_daily (
        id           SERIAL PRIMARY KEY,
        symbol       VARCHAR(10) NOT NULL,
        date         DATE         NOT NULL,
        open         DOUBLE PRECISION,
        high         DOUBLE PRECISION,
        low          DOUBLE PRECISION,
        close        DOUBLE PRECISION,
        adj_close    DOUBLE PRECISION,
        volume       BIGINT,
        dividends    DOUBLE PRECISION,
        stock_splits DOUBLE PRECISION,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date)
      )
    `);

    // Create fundamental_metrics table (from loadfundamentalmetrics.py)
    await query(`
      CREATE TABLE IF NOT EXISTS fundamental_metrics (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        market_cap BIGINT,
        pe_ratio DECIMAL(10,2),
        forward_pe DECIMAL(10,2),
        peg_ratio DECIMAL(10,2),
        price_to_book DECIMAL(10,2),
        price_to_sales DECIMAL(10,2),
        price_to_cash_flow DECIMAL(10,2),
        dividend_yield DECIMAL(8,4),
        dividend_rate DECIMAL(10,2),
        beta DECIMAL(8,4),
        fifty_two_week_high DECIMAL(10,2),
        fifty_two_week_low DECIMAL(10,2),
        revenue_per_share DECIMAL(10,2),
        revenue_growth DECIMAL(8,4),
        quarterly_revenue_growth DECIMAL(8,4),
        gross_profit BIGINT,
        ebitda BIGINT,
        operating_income BIGINT,
        net_income BIGINT,
        earnings_per_share DECIMAL(10,2),
        quarterly_earnings_growth DECIMAL(8,4),
        return_on_equity DECIMAL(8,4),
        return_on_assets DECIMAL(8,4),
        debt_to_equity DECIMAL(10,2),
        current_ratio DECIMAL(8,4),
        quick_ratio DECIMAL(8,4),
        book_value DECIMAL(10,2),
        shares_outstanding BIGINT,
        float_shares BIGINT,
        short_ratio DECIMAL(8,2),
        short_interest BIGINT,
        enterprise_value BIGINT,
        enterprise_to_revenue DECIMAL(10,2),
        enterprise_to_ebitda DECIMAL(10,2),
        sector VARCHAR(100),
        industry VARCHAR(200),
        full_time_employees INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol)
      )
    `);


    // Create company_profile table (from loadinfo.py)
    await query(`
      CREATE TABLE IF NOT EXISTS company_profile (
        ticker VARCHAR(10) PRIMARY KEY,
        short_name VARCHAR(100),
        long_name VARCHAR(200),
        display_name VARCHAR(200),
        quote_type VARCHAR(50),
        symbol_type VARCHAR(50),
        triggerable BOOLEAN,
        has_pre_post_market_data BOOLEAN,
        price_hint INT,
        max_age_sec INT,
        language VARCHAR(20),
        region VARCHAR(20),
        financial_currency VARCHAR(10),
        currency VARCHAR(10),
        market VARCHAR(50),
        market_state VARCHAR(50),
        exchange VARCHAR(50),
        time_zone VARCHAR(50),
        gmt_offset_ms BIGINT,
        regular_market_time BIGINT,
        exchange_timezone_name VARCHAR(100),
        exchange_timezone_short_name VARCHAR(50),
        is_esg_populated BOOLEAN,
        gmtOffset_ms BIGINT,
        market_cap BIGINT,
        shares_outstanding BIGINT,
        float_shares BIGINT,
        impl_volatility NUMERIC,
        beta NUMERIC,
        beta3year NUMERIC,
        sector VARCHAR(100),
        industry VARCHAR(200),
        full_time_employees INT,
        business_summary TEXT,
        company_officers_count INT,
        website VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create market_data table (from loadinfo.py)
    await query(`
      CREATE TABLE IF NOT EXISTS market_data (
        ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
        previous_close NUMERIC,
        regular_market_previous_close NUMERIC,
        open_price NUMERIC,
        regular_market_open NUMERIC,
        day_low NUMERIC,
        regular_market_day_low NUMERIC,
        day_high NUMERIC,
        regular_market_day_high NUMERIC,
        regular_market_price NUMERIC,
        current_price NUMERIC,
        post_market_price NUMERIC,
        post_market_change NUMERIC,
        post_market_change_pct NUMERIC,
        volume BIGINT,
        regular_market_volume BIGINT,
        avg_volume BIGINT,
        avg_volume_10days BIGINT,
        bid NUMERIC,
        ask NUMERIC,
        bid_size INT,
        ask_size INT,
        market_cap BIGINT,
        fifty_two_week_low NUMERIC,
        fifty_two_week_high NUMERIC,
        fifty_day_average NUMERIC,
        two_hundred_day_average NUMERIC,
        dividend_rate NUMERIC,
        dividend_yield NUMERIC,
        ex_dividend_date DATE,
        payout_ratio NUMERIC,
        five_year_avg_dividend_yield NUMERIC,
        trailing_annual_dividend_rate NUMERIC,
        trailing_annual_dividend_yield NUMERIC,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Add minimal test data for tests to work
    await query(`
      INSERT INTO company_profile (ticker, short_name, long_name, sector, industry, currency) VALUES
      ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics', 'USD'),
      ('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'Technology', 'Software', 'USD'),
      ('GOOGL', 'Alphabet Inc.', 'Alphabet Inc.', 'Technology', 'Internet Services', 'USD'),
      ('TSLA', 'Tesla, Inc.', 'Tesla, Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 'USD')
      ON CONFLICT (ticker) DO NOTHING
    `);

    // Add test data for market_data (to support metrics route)
    await query(`
      INSERT INTO market_data (ticker, current_price, market_cap, volume, fifty_two_week_high, fifty_two_week_low) VALUES
      ('AAPL', 151.50, 3500000000000, 25847600, 198.23, 124.17),
      ('MSFT', 350.85, 2800000000000, 18562300, 384.30, 212.21),
      ('GOOGL', 2855.75, 1750000000000, 1285400, 3030.93, 2193.62),
      ('TSLA', 247.25, 850000000000, 35847600, 414.50, 101.81)
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      INSERT INTO buy_sell_daily (symbol, date, timeframe, signal_type, confidence, price, rsi, macd, volume, volume_avg_10d, price_vs_ma20, price_vs_ma50, bollinger_position, support_level, resistance_level, pattern_score, momentum_score, risk_score) VALUES
      ('AAPL', '2024-01-01', 'daily', 'BUY', 75.5, 150.25, 45.2, 1.25, 65000000, 58000000, 2.3, 4.8, 65.5, 145.50, 155.75, 72.5, 68.3, 25.8),
      ('AAPL', '2024-01-02', 'daily', 'HOLD', 55.2, 151.50, 52.8, 0.85, 68000000, 61000000, 1.8, 3.2, 58.2, 147.25, 157.80, 62.1, 55.7, 35.2),
      ('MSFT', '2024-01-01', 'daily', 'SELL', 82.3, 350.75, 72.5, -0.95, 45000000, 42000000, -1.2, -2.8, 85.3, 340.25, 362.50, 78.9, 75.6, 28.5),
      ('MSFT', '2024-01-02', 'daily', 'BUY', 67.8, 349.95, 38.7, 1.15, 47000000, 44000000, 0.8, 2.1, 45.2, 342.50, 359.80, 65.4, 71.2, 32.1)
      ON CONFLICT (symbol, date, timeframe, signal_type) DO NOTHING
    `);

    await query(`
      INSERT INTO market_data (ticker, market_cap, current_price, previous_close, volume) VALUES
      ('AAPL', 3500000000000, 150.25, 149.50, 65000000),
      ('MSFT', 2800000000000, 350.75, 348.25, 45000000)
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      INSERT INTO stock_symbols (symbol, exchange, security_name, market_category, etf) VALUES
      ('AAPL', 'NASDAQ', 'Apple Inc.', 'Q', 'N'),
      ('MSFT', 'NASDAQ', 'Microsoft Corporation', 'Q', 'N'),
      ('GOOGL', 'NASDAQ', 'Alphabet Inc.', 'Q', 'N'),
      ('TSLA', 'NASDAQ', 'Tesla, Inc.', 'Q', 'N'),
      ('AMZN', 'NASDAQ', 'Amazon.com Inc.', 'Q', 'N'),
      ('NVDA', 'NASDAQ', 'NVIDIA Corporation', 'Q', 'N'),
      ('META', 'NASDAQ', 'Meta Platforms Inc.', 'Q', 'N')
    `);

    // Add comprehensive price_daily data matching loadlatestpricedaily.py structure
    // Use fixed dates to ensure market breadth calculation works
    await query(`
      INSERT INTO price_daily (symbol, date, open, high, low, close, volume) VALUES
      ('AAPL', '2024-01-02', 149.50, 151.25, 148.75, 150.25, 65000000),
      ('AAPL', '2024-01-01', 148.00, 150.50, 147.50, 149.50, 58000000),
      ('MSFT', '2024-01-02', 348.25, 352.50, 347.00, 350.75, 45000000),
      ('MSFT', '2024-01-01', 346.50, 349.25, 345.75, 348.25, 42000000),
      ('GOOGL', '2024-01-02', 2850.00, 2875.50, 2840.25, 2865.75, 15000000),
      ('GOOGL', '2024-01-01', 2825.00, 2860.00, 2820.00, 2845.50, 14500000),
      ('TSLA', '2024-01-02', 245.50, 248.75, 242.25, 247.80, 25000000),
      ('TSLA', '2024-01-01', 240.00, 246.50, 238.75, 244.25, 23000000),
      ('AMZN', '2024-01-02', 3150.00, 3175.25, 3145.50, 3168.90, 12000000),
      ('AMZN', '2024-01-01', 3140.00, 3155.75, 3135.25, 3152.40, 11500000),
      ('NVDA', '2024-01-02', 875.00, 890.25, 870.50, 885.75, 18000000),
      ('NVDA', '2024-01-01', 860.00, 880.00, 855.25, 872.50, 17500000),
      ('META', '2024-01-02', 485.00, 492.75, 482.25, 489.50, 8500000),
      ('META', '2024-01-01', 478.00, 487.50, 475.75, 483.25, 8200000)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    await query(`
      INSERT INTO fundamental_metrics (symbol, market_cap, pe_ratio, forward_pe, price_to_book, price_to_sales, dividend_yield) VALUES
      ('AAPL', 3500000000000, 25.5, 22.8, 45.2, 7.8, 0.46),
      ('MSFT', 2800000000000, 28.7, 24.1, 12.5, 12.3, 0.72),
      ('GOOGL', 2100000000000, 23.4, 20.1, 6.8, 5.9, 0.00),
      ('TSLA', 850000000000, 52.1, 45.6, 12.3, 8.7, 0.00),
      ('AMZN', 1750000000000, 35.2, 28.9, 8.4, 2.8, 0.00),
      ('NVDA', 2200000000000, 28.9, 25.4, 15.6, 22.1, 0.09),
      ('META', 800000000000, 18.7, 16.2, 6.1, 7.3, 0.00)
      ON CONFLICT (symbol) DO NOTHING
    `);

    // Add earnings_history test data
    await query(`
      INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate, surprise_percent) VALUES
      ('AAPL', '2024-01-01', 2.18, 2.10, 3.8),
      ('AAPL', '2023-10-01', 1.89, 1.85, 2.2),
      ('MSFT', '2024-01-01', 2.93, 2.85, 2.8),
      ('MSFT', '2023-10-01', 2.69, 2.65, 1.5),
      ('GOOGL', '2024-01-01', 1.64, 1.59, 3.1),
      ('TSLA', '2024-01-01', 0.71, 0.73, -2.7)
      ON CONFLICT (symbol, quarter) DO NOTHING
    `);

    // Add earnings_estimates test data
    await query(`
      INSERT INTO earnings_estimates (symbol, period, avg_estimate, low_estimate, high_estimate, year_ago_eps, number_of_analysts, growth) VALUES
      ('AAPL', 'Q1', 2.20, 2.15, 2.25, 2.10, 8, 4.8),
      ('AAPL', 'Q2', 2.10, 2.05, 2.18, 2.02, 9, 4.0),
      ('MSFT', 'Q1', 2.95, 2.88, 3.02, 2.85, 12, 3.5),
      ('MSFT', 'Q2', 2.85, 2.78, 2.92, 2.75, 11, 3.6),
      ('GOOGL', 'Q1', 1.68, 1.60, 1.75, 1.59, 15, 5.7),
      ('TSLA', 'Q1', 0.75, 0.70, 0.82, 0.73, 6, 2.7)
      ON CONFLICT (symbol, period) DO NOTHING
    `);

    // Add earnings_metrics test data
    await query(`
      INSERT INTO earnings_metrics (symbol, report_date, eps_growth_1q, eps_growth_2q, eps_surprise_last_q, annual_eps_growth_1y) VALUES
      ('AAPL', '2024-01-01', 3.8, 5.2, 3.8, 12.5),
      ('MSFT', '2024-01-01', 2.8, 4.1, 2.8, 8.9),
      ('GOOGL', '2024-01-01', 3.1, 6.2, 3.1, 15.2),
      ('TSLA', '2024-01-01', -2.7, 1.5, -2.7, 25.8)
      ON CONFLICT (symbol, report_date) DO NOTHING
    `);

    // Add analyst_upgrade_downgrade test data
    await query(`
      INSERT INTO analyst_upgrade_downgrade (symbol, firm, action, from_grade, to_grade, date, details) VALUES
      ('AAPL', 'Goldman Sachs', 'upgrade', 'Hold', 'Buy', '2024-01-15', 'Strong iPhone sales'),
      ('MSFT', 'Morgan Stanley', 'upgrade', 'Equal Weight', 'Overweight', '2024-01-10', 'Cloud growth acceleration'),
      ('GOOGL', 'JP Morgan', 'maintain', 'Overweight', 'Overweight', '2024-01-12', 'AI momentum continues'),
      ('TSLA', 'Barclays', 'downgrade', 'Buy', 'Hold', '2024-01-08', 'Delivery concerns')
    `);

    // Add test table for connection pool stress tests
    await query(`
      CREATE TABLE IF NOT EXISTS test_transaction_stress (
        id SERIAL PRIMARY KEY,
        value INTEGER NOT NULL,
        updated_by VARCHAR(50),
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Add position_history table for trades tests
    await query(`
      CREATE TABLE IF NOT EXISTS position_history (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        side VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,4) NOT NULL,
        avg_entry_price DECIMAL(12,4),
        avg_exit_price DECIMAL(12,4),
        net_pnl DECIMAL(15,4),
        return_percentage DECIMAL(8,4),
        opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at TIMESTAMP,
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO test_transaction_stress (value, updated_by) VALUES
      (100, 'initial')
    `);

    await query(`
      INSERT INTO position_history (user_id, symbol, side, quantity, avg_entry_price, current_price, net_pnl, return_percentage, status, opened_at, closed_at) VALUES
      ('dev-user-bypass', 'AAPL', 'long', 100, 150.25, 155.75, 550.00, 3.66, 'closed', '2024-01-01 10:00:00', '2024-01-02 15:30:00'),
      ('dev-user-bypass', 'MSFT', 'long', 50, 348.25, 352.50, 212.50, 1.22, 'closed', '2024-01-01 11:00:00', '2024-01-02 14:00:00'),
      ('dev-user-bypass', 'GOOGL', 'long', 25, 2850.00, 2865.75, 393.75, 0.55, 'open', '2024-01-02 09:30:00', NULL),
      ('dev-user-bypass', 'TSLA', 'short', 75, 247.80, 244.25, 266.25, 1.43, 'closed', '2024-01-01 12:00:00', '2024-01-02 16:00:00')
      ON CONFLICT (id) DO NOTHING
    `);

    // Create trades table for trading functionality (matching create_trades_table.sql)
    await query(`
      CREATE TABLE IF NOT EXISTS trades (
        trade_id VARCHAR(255) PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        type VARCHAR(20) NOT NULL DEFAULT 'market',
        limit_price DECIMAL(10,4),
        stop_price DECIMAL(10,4),
        time_in_force VARCHAR(10) DEFAULT 'day',
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        executed_at TIMESTAMP,
        average_fill_price DECIMAL(10,4),
        filled_quantity INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Add sample trades test data
    await query(`
      INSERT INTO trades (trade_id, user_id, symbol, side, quantity, type, status, created_at) VALUES
      ('test-trade-1', 'test-user', 'AAPL', 'buy', 100, 'market', 'filled', NOW() - INTERVAL '1 day'),
      ('test-trade-2', 'test-user', 'MSFT', 'sell', 50, 'limit', 'pending', NOW() - INTERVAL '2 hours'),
      ('test-trade-3', 'test-user', 'TSLA', 'buy', 25, 'market', 'filled', NOW() - INTERVAL '1 week')
      ON CONFLICT (trade_id) DO NOTHING
    `);

    // Create sentiment tables matching loader structures

    // Fear & Greed Index table (from loadfeargreed.py)
    await query(`
      CREATE TABLE IF NOT EXISTS fear_greed_index (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL UNIQUE,
        index_value DOUBLE PRECISION,
        rating VARCHAR(50),
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Add rating column if it doesn't exist (for existing tables)
    try {
      await query(`
        ALTER TABLE fear_greed_index
        ADD COLUMN IF NOT EXISTS rating VARCHAR(50)
      `);
    } catch (error) {
      // Ignore error if column already exists
      if (!error.message.includes('already exists')) {
        console.warn('Could not add rating column to fear_greed_index:', error.message);
      }
    }

    // NAAIM table (from loadnaaim.py)
    await query(`
      CREATE TABLE IF NOT EXISTS naaim (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL UNIQUE,
        naaim_number_mean DOUBLE PRECISION,
        bearish DOUBLE PRECISION,
        quart1 DOUBLE PRECISION,
        quart2 DOUBLE PRECISION,
        quart3 DOUBLE PRECISION,
        bullish DOUBLE PRECISION,
        deviation DOUBLE PRECISION,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // AAII Sentiment table (from loadaaiidata.py)
    await query(`
      CREATE TABLE IF NOT EXISTS aaii_sentiment (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL UNIQUE,
        bullish DOUBLE PRECISION,
        neutral DOUBLE PRECISION,
        bearish DOUBLE PRECISION,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Economic Data table (from loadecondata.py)
    await query(`
      CREATE TABLE IF NOT EXISTS economic_data (
        id SERIAL PRIMARY KEY,
        series_id VARCHAR(100) NOT NULL,
        date DATE NOT NULL,
        value DOUBLE PRECISION,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(series_id, date)
      )
    `);

    // Create dividend_history table for dividend functionality
    await query(`
      CREATE TABLE IF NOT EXISTS dividend_history (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        ex_dividend_date DATE,
        record_date DATE,
        payment_date DATE,
        dividend_amount DECIMAL(10,4),
        currency VARCHAR(10) DEFAULT 'USD',
        frequency VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Add test data for sentiment indicators
    await query(`
      INSERT INTO fear_greed_index (date, value, rating) VALUES
      ('2024-01-02', 55, 'Greed'),
      ('2024-01-01', 48, 'Neutral')
      ON CONFLICT (date) DO NOTHING
    `);

    await query(`
      INSERT INTO naaim (date, naaim_number_mean, bearish, bullish) VALUES
      ('2024-01-02', 65.5, 15.2, 78.3),
      ('2024-01-01', 62.1, 18.7, 75.9)
      ON CONFLICT (date) DO NOTHING
    `);

    await query(`
      INSERT INTO aaii_sentiment (date, bullish, neutral, bearish) VALUES
      ('2024-01-02', 42.5, 32.1, 25.4),
      ('2024-01-01', 39.8, 35.2, 25.0)
      ON CONFLICT (date) DO NOTHING
    `);

    await query(`
      INSERT INTO economic_data (series_id, date, value) VALUES
      ('GDP', '2024-01-01', 26854.6),
      ('UNEMPLOYMENT_RATE', '2024-01-01', 3.7),
      ('INFLATION_RATE', '2024-01-01', 3.2),
      ('FEDERAL_FUNDS_RATE', '2024-01-01', 5.25),
      ('VIX', '2024-01-02', 18.5)
      ON CONFLICT (series_id, date) DO NOTHING
    `);

    // Add test data for dividend_history
    await query(`
      INSERT INTO dividend_history (symbol, ex_dividend_date, record_date, payment_date, dividend_amount, frequency) VALUES
      ('AAPL', '2024-02-08', '2024-02-12', '2024-02-15', 0.24, 'quarterly'),
      ('AAPL', '2023-11-09', '2023-11-13', '2023-11-16', 0.24, 'quarterly'),
      ('MSFT', '2024-02-13', '2024-02-15', '2024-03-14', 0.75, 'quarterly'),
      ('MSFT', '2023-11-14', '2023-11-16', '2023-12-14', 0.75, 'quarterly'),
      ('GOOGL', '2024-02-26', '2024-02-27', '2024-03-15', 0.20, 'quarterly')
    `);

    // Create technical_data_daily table matching loadtechnicalsdaily.py
    await query(`
      CREATE TABLE IF NOT EXISTS technical_data_daily (
        symbol VARCHAR(50),
        date TIMESTAMP,
        rsi DOUBLE PRECISION,
        macd DOUBLE PRECISION,
        macd_signal DOUBLE PRECISION,
        macd_hist DOUBLE PRECISION,
        mom DOUBLE PRECISION,
        roc DOUBLE PRECISION,
        adx DOUBLE PRECISION,
        plus_di DOUBLE PRECISION,
        minus_di DOUBLE PRECISION,
        atr DOUBLE PRECISION,
        ad DOUBLE PRECISION,
        cmf DOUBLE PRECISION,
        mfi DOUBLE PRECISION,
        td_sequential DOUBLE PRECISION,
        td_combo DOUBLE PRECISION,
        marketwatch DOUBLE PRECISION,
        dm DOUBLE PRECISION,
        sma_10 DOUBLE PRECISION,
        sma_20 DOUBLE PRECISION,
        sma_50 DOUBLE PRECISION,
        sma_150 DOUBLE PRECISION,
        sma_200 DOUBLE PRECISION,
        ema_4 DOUBLE PRECISION,
        ema_9 DOUBLE PRECISION,
        ema_21 DOUBLE PRECISION,
        bbands_lower DOUBLE PRECISION,
        bbands_middle DOUBLE PRECISION,
        bbands_upper DOUBLE PRECISION,
        pivot_high DOUBLE PRECISION,
        pivot_low DOUBLE PRECISION,
        pivot_high_triggered DOUBLE PRECISION,
        pivot_low_triggered DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    // Create technical_data_weekly table
    await query(`
      CREATE TABLE IF NOT EXISTS technical_data_weekly (
        symbol VARCHAR(50),
        date TIMESTAMP,
        rsi DOUBLE PRECISION,
        macd DOUBLE PRECISION,
        macd_signal DOUBLE PRECISION,
        macd_hist DOUBLE PRECISION,
        mom DOUBLE PRECISION,
        roc DOUBLE PRECISION,
        adx DOUBLE PRECISION,
        plus_di DOUBLE PRECISION,
        minus_di DOUBLE PRECISION,
        atr DOUBLE PRECISION,
        ad DOUBLE PRECISION,
        cmf DOUBLE PRECISION,
        mfi DOUBLE PRECISION,
        sma_10 DOUBLE PRECISION,
        sma_20 DOUBLE PRECISION,
        sma_50 DOUBLE PRECISION,
        sma_150 DOUBLE PRECISION,
        sma_200 DOUBLE PRECISION,
        ema_4 DOUBLE PRECISION,
        ema_9 DOUBLE PRECISION,
        ema_21 DOUBLE PRECISION,
        bbands_lower DOUBLE PRECISION,
        bbands_middle DOUBLE PRECISION,
        bbands_upper DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    // Create technical_data_monthly table
    await query(`
      CREATE TABLE IF NOT EXISTS technical_data_monthly (
        symbol VARCHAR(50),
        date TIMESTAMP,
        rsi DOUBLE PRECISION,
        macd DOUBLE PRECISION,
        macd_signal DOUBLE PRECISION,
        macd_hist DOUBLE PRECISION,
        mom DOUBLE PRECISION,
        roc DOUBLE PRECISION,
        adx DOUBLE PRECISION,
        plus_di DOUBLE PRECISION,
        minus_di DOUBLE PRECISION,
        atr DOUBLE PRECISION,
        ad DOUBLE PRECISION,
        cmf DOUBLE PRECISION,
        mfi DOUBLE PRECISION,
        sma_10 DOUBLE PRECISION,
        sma_20 DOUBLE PRECISION,
        sma_50 DOUBLE PRECISION,
        sma_150 DOUBLE PRECISION,
        sma_200 DOUBLE PRECISION,
        ema_4 DOUBLE PRECISION,
        ema_9 DOUBLE PRECISION,
        ema_21 DOUBLE PRECISION,
        bbands_lower DOUBLE PRECISION,
        bbands_middle DOUBLE PRECISION,
        bbands_upper DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    // Create financial statement tables that financials route expects
    await query(`
      CREATE TABLE IF NOT EXISTS quarterly_income_statement (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        item_name VARCHAR(100) NOT NULL,
        value NUMERIC,
        PRIMARY KEY (symbol, date, item_name)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS annual_income_statement (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        item_name VARCHAR(100) NOT NULL,
        value NUMERIC,
        PRIMARY KEY (symbol, date, item_name)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        item_name VARCHAR(100) NOT NULL,
        value NUMERIC,
        PRIMARY KEY (symbol, date, item_name)
      )
    `);

    await query(`DROP TABLE IF EXISTS annual_balance_sheet`);
    await query(`
      CREATE TABLE annual_balance_sheet (
        symbol VARCHAR(10) NOT NULL,
        ticker VARCHAR(10),
        year INTEGER,
        date DATE,
        item_name VARCHAR(100),
        value NUMERIC,
        total_assets NUMERIC,
        total_liabilities NUMERIC,
        PRIMARY KEY (symbol, date, item_name)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        item_name VARCHAR(100) NOT NULL,
        value NUMERIC,
        PRIMARY KEY (symbol, date, item_name)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS annual_cash_flow (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        item_name VARCHAR(100) NOT NULL,
        value NUMERIC,
        PRIMARY KEY (symbol, date, item_name)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS financial_ratios (
        symbol VARCHAR(10) NOT NULL,
        fiscal_year INTEGER NOT NULL,
        price_to_earnings NUMERIC,
        price_to_book NUMERIC,
        debt_to_equity NUMERIC,
        current_ratio NUMERIC,
        quick_ratio NUMERIC,
        profit_margin NUMERIC,
        return_on_equity NUMERIC,
        return_on_assets NUMERIC,
        PRIMARY KEY (symbol, fiscal_year)
      )
    `);

    // Add test data for price_daily (to support technical route JOINs)
    await query(`
      INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits) VALUES
      ('AAPL', '2024-01-02', 150.25, 152.80, 149.85, 151.50, 151.50, 25847600, 0.00, 0.00),
      ('AAPL', '2024-01-01', 149.80, 151.25, 148.95, 150.85, 150.85, 23985400, 0.00, 0.00),
      ('MSFT', '2024-01-02', 348.50, 352.75, 347.25, 350.85, 350.85, 18562300, 0.00, 0.00),
      ('MSFT', '2024-01-01', 347.25, 350.50, 346.80, 349.95, 349.95, 16847200, 0.00, 0.00),
      ('GOOGL', '2024-01-02', 2845.25, 2865.80, 2835.50, 2855.75, 2855.75, 1285400, 0.00, 0.00),
      ('TSLA', '2024-01-02', 245.50, 248.85, 244.25, 247.25, 247.25, 35847600, 0.00, 0.00)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    // Add test data for fundamental_metrics (to support metrics route)
    await query(`
      INSERT INTO fundamental_metrics (symbol, market_cap, pe_ratio, forward_pe, price_to_book, price_to_sales, dividend_yield, revenue_growth, quarterly_earnings_growth, return_on_equity, return_on_assets, debt_to_equity, sector, industry) VALUES
      ('AAPL', 3500000000000, 25.5, 22.8, 8.2, 6.8, 0.0045, 0.08, 0.12, 0.18, 0.08, 0.35, 'Technology', 'Consumer Electronics'),
      ('MSFT', 2800000000000, 28.2, 24.5, 12.5, 9.2, 0.0028, 0.15, 0.18, 0.22, 0.12, 0.28, 'Technology', 'Software'),
      ('GOOGL', 1750000000000, 18.5, 16.8, 4.2, 5.1, 0.0000, 0.12, 0.08, 0.15, 0.09, 0.18, 'Technology', 'Internet Services'),
      ('TSLA', 850000000000, 45.8, 38.2, 12.8, 8.5, 0.0000, 0.25, 0.35, 0.28, 0.15, 0.42, 'Consumer Cyclical', 'Auto Manufacturers')
      ON CONFLICT (symbol) DO NOTHING
    `);

    // Add test data for technical indicators
    await query(`
      INSERT INTO technical_data_daily (symbol, date, rsi, macd, macd_signal, sma_20, sma_50, sma_200, adx, atr) VALUES
      ('AAPL', '2024-01-02', 65.5, 0.85, 0.75, 151.20, 148.50, 145.25, 25.8, 2.45),
      ('AAPL', '2024-01-01', 62.8, 0.72, 0.68, 150.80, 148.25, 145.10, 24.2, 2.38),
      ('MSFT', '2024-01-02', 58.2, 1.25, 1.15, 350.25, 347.50, 342.15, 28.5, 4.85),
      ('MSFT', '2024-01-01', 55.9, 1.08, 1.02, 349.80, 347.25, 341.95, 27.8, 4.72),
      ('GOOGL', '2024-01-02', 45.8, -0.35, -0.25, 2850.50, 2825.75, 2785.25, 15.2, 35.85),
      ('TSLA', '2024-01-02', 72.5, 2.15, 1.95, 246.80, 242.25, 235.50, 35.8, 8.95)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    await query(`
      INSERT INTO technical_data_weekly (symbol, date, rsi, macd, macd_signal, sma_20, sma_50, sma_200) VALUES
      ('AAPL', '2024-01-01', 60.2, 0.95, 0.88, 150.50, 147.25, 144.80),
      ('MSFT', '2024-01-01', 55.8, 1.35, 1.25, 348.75, 345.50, 340.25),
      ('GOOGL', '2024-01-01', 48.5, -0.25, -0.15, 2840.25, 2815.50, 2775.00)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    await query(`
      INSERT INTO technical_data_monthly (symbol, date, rsi, macd, macd_signal, sma_20, sma_50, sma_200) VALUES
      ('AAPL', '2024-01-01', 58.5, 1.15, 1.05, 149.25, 145.75, 142.50),
      ('MSFT', '2024-01-01', 52.8, 1.55, 1.45, 346.50, 342.25, 337.75),
      ('GOOGL', '2024-01-01', 51.2, -0.15, -0.05, 2825.75, 2800.25, 2760.50)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    // Add test data for financial statements
    await query(`
      INSERT INTO annual_income_statement (symbol, date, item_name, value) VALUES
      ('AAPL', '2023-12-31', 'total_revenue', 383285000000),
      ('AAPL', '2023-12-31', 'cost_of_revenue', 214137000000),
      ('AAPL', '2023-12-31', 'gross_profit', 169148000000),
      ('AAPL', '2023-12-31', 'operating_expenses', 55013000000),
      ('AAPL', '2023-12-31', 'operating_income', 114135000000),
      ('AAPL', '2023-12-31', 'net_income', 96995000000),
      ('MSFT', '2023-12-31', 'total_revenue', 211915000000),
      ('MSFT', '2023-12-31', 'cost_of_revenue', 65525000000),
      ('MSFT', '2023-12-31', 'gross_profit', 146390000000),
      ('MSFT', '2023-12-31', 'operating_income', 88523000000),
      ('MSFT', '2023-12-31', 'net_income', 72361000000)
      ON CONFLICT (symbol, date, item_name) DO NOTHING
    `);

    await query(`
      INSERT INTO quarterly_income_statement (symbol, date, item_name, value) VALUES
      ('AAPL', '2024-03-31', 'total_revenue', 90753000000),
      ('AAPL', '2024-03-31', 'cost_of_revenue', 54413000000),
      ('AAPL', '2024-03-31', 'gross_profit', 36340000000),
      ('AAPL', '2024-03-31', 'net_income', 23636000000),
      ('MSFT', '2024-03-31', 'total_revenue', 61858000000),
      ('MSFT', '2024-03-31', 'cost_of_revenue', 19715000000),
      ('MSFT', '2024-03-31', 'gross_profit', 42143000000),
      ('MSFT', '2024-03-31', 'net_income', 21939000000)
      ON CONFLICT (symbol, date, item_name) DO NOTHING
    `);

    await query(`
      INSERT INTO annual_balance_sheet (symbol, ticker, year, date, item_name, value, total_assets, total_liabilities) VALUES
      ('AAPL', 'AAPL', 2023, '2023-12-31', 'total_assets', 352755000000, 352755000000, 290437000000),
      ('AAPL', 'AAPL', 2023, '2023-12-31', 'total_liabilities', 290437000000, 352755000000, 290437000000),
      ('MSFT', 'MSFT', 2023, '2023-12-31', 'total_assets', 411976000000, 411976000000, 205753000000),
      ('MSFT', 'MSFT', 2023, '2023-12-31', 'total_liabilities', 205753000000, 411976000000, 205753000000)
      ON CONFLICT (symbol, date, item_name) DO NOTHING
    `);

    await query(`
      INSERT INTO quarterly_balance_sheet (symbol, date, item_name, value) VALUES
      ('AAPL', '2024-03-31', 'total_assets', 364980000000),
      ('AAPL', '2024-03-31', 'total_liabilities', 298020000000),
      ('MSFT', '2024-03-31', 'total_assets', 512715000000),
      ('MSFT', '2024-03-31', 'total_liabilities', 240781000000)
      ON CONFLICT (symbol, date, item_name) DO NOTHING
    `);

    await query(`
      INSERT INTO annual_cash_flow (symbol, date, item_name, value) VALUES
      ('AAPL', '2023-12-31', 'operating_cash_flow', 110543000000),
      ('AAPL', '2023-12-31', 'investing_cash_flow', -3705000000),
      ('AAPL', '2023-12-31', 'financing_cash_flow', -106040000000),
      ('MSFT', '2023-12-31', 'operating_cash_flow', 87582000000),
      ('MSFT', '2023-12-31', 'investing_cash_flow', -28721000000),
      ('MSFT', '2023-12-31', 'financing_cash_flow', -50346000000)
      ON CONFLICT (symbol, date, item_name) DO NOTHING
    `);

    await query(`
      INSERT INTO quarterly_cash_flow (symbol, date, item_name, value) VALUES
      ('AAPL', '2024-03-31', 'operating_cash_flow', 28309000000),
      ('AAPL', '2024-03-31', 'investing_cash_flow', -966000000),
      ('AAPL', '2024-03-31', 'financing_cash_flow', -26700000000),
      ('MSFT', '2024-03-31', 'operating_cash_flow', 21563000000),
      ('MSFT', '2024-03-31', 'investing_cash_flow', -9652000000),
      ('MSFT', '2024-03-31', 'financing_cash_flow', -7932000000)
      ON CONFLICT (symbol, date, item_name) DO NOTHING
    `);

    await query(`
      INSERT INTO financial_ratios (symbol, fiscal_year, price_to_earnings, price_to_book, debt_to_equity, current_ratio, quick_ratio, profit_margin, return_on_equity, return_on_assets) VALUES
      ('AAPL', 2023, 25.3, 8.2, 0.35, 1.2, 1.1, 0.253, 0.18, 0.08),
      ('MSFT', 2023, 28.2, 12.5, 0.28, 2.1, 1.9, 0.341, 0.22, 0.12),
      ('GOOGL', 2023, 18.5, 4.2, 0.18, 3.5, 3.2, 0.185, 0.15, 0.09),
      ('TSLA', 2023, 45.8, 12.8, 0.42, 1.8, 1.6, 0.082, 0.28, 0.15)
      ON CONFLICT (symbol, fiscal_year) DO NOTHING
    `);

    // Create volume_alerts table for alerts routes
    await query(`
      CREATE TABLE IF NOT EXISTS volume_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        threshold_multiplier DECIMAL(5,2) NOT NULL,
        condition VARCHAR(20) NOT NULL,
        notification_methods JSONB DEFAULT '["email"]',
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO volume_alerts (user_id, symbol, threshold_multiplier, condition, notification_methods) VALUES
      ('test-user-1', 'AAPL', 2.0, 'above', '["email"]'),
      ('test-user-2', 'MSFT', 1.5, 'above', '["sms"]')
      ON CONFLICT DO NOTHING
    `);

    // Create volume_analysis table for alerts routes
    await query(`
      CREATE TABLE IF NOT EXISTS volume_analysis (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        current_volume BIGINT,
        avg_volume_20d BIGINT,
        volume_ratio DECIMAL(8,6),
        volume_trend VARCHAR(20),
        analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO volume_analysis (symbol, current_volume, avg_volume_20d, volume_ratio, volume_trend) VALUES
      ('AAPL', 65000000, 58000000, 1.12, 'increasing'),
      ('MSFT', 45000000, 42000000, 1.07, 'stable')
      ON CONFLICT DO NOTHING
    `);

    // Create portfolio_metadata table for portfolio routes
    await query(`DROP TABLE IF EXISTS portfolio_metadata`);
    await query(`
      CREATE TABLE portfolio_metadata (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        broker VARCHAR(50) NOT NULL,
        last_rebalance_date TIMESTAMP WITH TIME ZONE,
        rebalance_count INTEGER DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_user_broker_metadata UNIQUE (user_id, broker)
      )
    `);

    await query(`
      INSERT INTO portfolio_metadata (user_id, broker, last_rebalance_date, rebalance_count) VALUES
      ('test-user-1', 'alpaca', '2024-01-01', 1),
      ('test-user-2', 'alpaca', '2024-01-02', 2)
      ON CONFLICT (user_id, broker) DO NOTHING
    `);

    // Create alert_settings table for alerts routes
    await query(`
      CREATE TABLE IF NOT EXISTS alert_settings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL UNIQUE,
        notification_preferences JSONB DEFAULT '{}',
        delivery_settings JSONB DEFAULT '{}',
        alert_categories JSONB DEFAULT '{}',
        watchlist_settings JSONB DEFAULT '{}',
        advanced_settings JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO alert_settings (user_id, notification_preferences, delivery_settings) VALUES
      ('test-user-1', '{"email": true, "sms": false}', '{"frequency": "immediate"}'),
      ('test-user-2', '{"email": false, "sms": true}', '{"frequency": "daily"}')
      ON CONFLICT (user_id) DO NOTHING
    `);

    // Create daily_volume_history table for alerts routes
    await query(`
      CREATE TABLE IF NOT EXISTS daily_volume_history (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        trading_date DATE NOT NULL,
        volume BIGINT,
        avg_volume_20d BIGINT,
        volume_ratio DECIMAL(8,6),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, trading_date)
      )
    `);

    await query(`
      INSERT INTO daily_volume_history (symbol, trading_date, volume, avg_volume_20d, volume_ratio) VALUES
      ('AAPL', '2024-01-02', 65000000, 58000000, 1.12),
      ('AAPL', '2024-01-01', 58000000, 55000000, 1.05),
      ('MSFT', '2024-01-02', 45000000, 42000000, 1.07),
      ('MSFT', '2024-01-01', 42000000, 40000000, 1.05)
      ON CONFLICT (symbol, trading_date) DO NOTHING
    `);

    // Create technical_alerts table for alerts routes
    await query(`DROP TABLE IF EXISTS technical_alerts`);
    await query(`
      CREATE TABLE technical_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        indicator_type VARCHAR(50) NOT NULL,
        condition VARCHAR(20) NOT NULL,
        threshold_value DECIMAL(10,4),
        current_value DECIMAL(10,4),
        notification_methods JSONB DEFAULT '["email"]',
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        triggered_at TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO technical_alerts (user_id, symbol, indicator_type, condition, threshold_value, notification_methods) VALUES
      ('test-user-1', 'AAPL', 'RSI', 'below', 30.0, '["email"]'),
      ('test-user-2', 'MSFT', 'MACD', 'crosses_above', 0.0, '["sms"]')
      ON CONFLICT DO NOTHING
    `);

    // Create orders table for orders routes
    await query(`DROP TABLE IF EXISTS orders`);
    await query(`
      CREATE TABLE orders (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        order_type VARCHAR(20) NOT NULL DEFAULT 'market',
        limit_price DECIMAL(10,2),
        stop_price DECIMAL(10,2),
        time_in_force VARCHAR(10) DEFAULT 'day',
        status VARCHAR(20) DEFAULT 'pending',
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        filled_at TIMESTAMP,
        filled_quantity INTEGER DEFAULT 0,
        average_price DECIMAL(10,2),
        broker VARCHAR(50) DEFAULT 'alpaca',
        notes TEXT,
        extended_hours BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO orders (user_id, symbol, side, quantity, order_type, limit_price, status, submitted_at, broker) VALUES
      ('test-user-1', 'AAPL', 'buy', 100, 'limit', 150.00, 'filled', '2024-01-01', 'alpaca'),
      ('test-user-2', 'MSFT', 'sell', 50, 'market', NULL, 'pending', '2024-01-02', 'alpaca')
    `);

    // Create watchlist tables for watchlist routes
    await query(`DROP TABLE IF EXISTS watchlist_items`);
    await query(`DROP TABLE IF EXISTS watchlists`);
    await query(`
      CREATE TABLE watchlists (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        is_default BOOLEAN DEFAULT FALSE,
        is_public BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      CREATE TABLE watchlist_items (
        id SERIAL PRIMARY KEY,
        watchlist_id INTEGER REFERENCES watchlists(id) ON DELETE CASCADE,
        symbol VARCHAR(10) NOT NULL,
        notes TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(watchlist_id, symbol)
      )
    `);

    await query(`
      INSERT INTO watchlists (user_id, name, description, is_default, is_public) VALUES
      ('test-user-1', 'My Portfolio', 'Main investment portfolio', true, false),
      ('test-user-2', 'Tech Stocks', 'Technology sector stocks', false, true)
    `);

    await query(`
      INSERT INTO watchlist_items (watchlist_id, symbol, notes) VALUES
      (1, 'AAPL', 'Apple Inc'),
      (1, 'MSFT', 'Microsoft'),
      (2, 'GOOGL', 'Google/Alphabet')
    `);

    console.log('✅ Database tables created matching loader structure');
  } catch (error) {
    console.warn('Could not create test database tables:', error.message);
  }

  console.log("🔧 Global test setup complete");
};