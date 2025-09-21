// Global setup for tests - ensures database tables match loader structure
module.exports = async () => {
  process.env.NODE_ENV = "test";

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

    // Create buy_sell_daily table (from loadlatestbuyselldaily.py)
    await query(`
      CREATE TABLE IF NOT EXISTS buy_sell_daily (
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
        PRIMARY KEY (symbol, date, timeframe, signal_type)
      )
    `);

    // Create earnings_history table (from loadearningshistory.py)
    await query(`
      CREATE TABLE IF NOT EXISTS earnings_history (
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

    await query(`
      CREATE TABLE IF NOT EXISTS price_daily (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open DECIMAL(12,4),
        high DECIMAL(12,4),
        low DECIMAL(12,4),
        close DECIMAL(12,4),
        volume BIGINT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS fundamental_metrics (
        symbol VARCHAR(10) NOT NULL,
        market_cap BIGINT,
        pe_ratio DECIMAL(10,2),
        forward_pe DECIMAL(10,2),
        price_to_book DECIMAL(10,2),
        price_to_sales DECIMAL(10,2),
        dividend_yield DECIMAL(8,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol)
      )
    `);

    // Add minimal test data for tests to work
    await query(`
      INSERT INTO company_profile (ticker, short_name, long_name, sector, industry, currency) VALUES
      ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics', 'USD'),
      ('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'Technology', 'Software', 'USD')
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      INSERT INTO buy_sell_daily (symbol, date, timeframe, signal_type, confidence, price, rsi, macd, volume, volume_avg_10d, price_vs_ma20, price_vs_ma50, bollinger_position, support_level, resistance_level, pattern_score, momentum_score, risk_score) VALUES
      ('AAPL', '2024-01-01', 'daily', 'buy', 85.5, 150.25, 25.5, 1.25, 65000000, 60000000, 5.2, 8.1, 0.25, 145.50, 155.75, 78.5, 82.3, 22.1),
      ('AAPL', '2024-01-02', 'daily', 'hold', 60.0, 152.75, 45.2, 0.85, 68000000, 61000000, 6.1, 9.2, 0.45, 147.25, 157.50, 65.2, 58.7, 35.8),
      ('MSFT', '2024-01-01', 'daily', 'sell', 75.3, 350.50, 70.8, -0.75, 45000000, 43000000, -2.5, -1.8, 0.85, 340.25, 365.75, 25.8, 18.5, 78.2),
      ('MSFT', '2024-01-02', 'daily', 'buy', 80.2, 348.25, 30.1, 0.95, 47000000, 44000000, 1.2, 3.8, 0.35, 342.50, 358.00, 82.1, 75.6, 28.9)
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
      ON CONFLICT DO NOTHING
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
      INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate, eps_difference, surprise_percent) VALUES
      ('AAPL', '2024-01-01', 2.18, 2.10, 0.08, 3.8),
      ('AAPL', '2023-10-01', 1.89, 1.85, 0.04, 2.2),
      ('MSFT', '2024-01-01', 2.93, 2.85, 0.08, 2.8),
      ('MSFT', '2023-10-01', 2.69, 2.65, 0.04, 1.5),
      ('GOOGL', '2024-01-01', 1.64, 1.59, 0.05, 3.1),
      ('TSLA', '2024-01-01', 0.71, 0.73, -0.02, -2.7)
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
      ON CONFLICT DO NOTHING
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
      ON CONFLICT DO NOTHING
    `);

    await query(`
      INSERT INTO position_history (user_id, symbol, side, quantity, avg_entry_price, avg_exit_price, net_pnl, return_percentage, status, opened_at, closed_at) VALUES
      ('dev-user-bypass', 'AAPL', 'buy', 100, 150.25, 155.75, 550.00, 3.66, 'closed', '2024-01-01 10:00:00', '2024-01-02 15:30:00'),
      ('dev-user-bypass', 'MSFT', 'buy', 50, 348.25, 352.50, 212.50, 1.22, 'closed', '2024-01-01 11:00:00', '2024-01-02 14:00:00'),
      ('dev-user-bypass', 'GOOGL', 'buy', 25, 2850.00, 2865.75, 393.75, 0.55, 'active', '2024-01-02 09:30:00', NULL),
      ('dev-user-bypass', 'TSLA', 'sell', 75, 247.80, 244.25, 266.25, 1.43, 'closed', '2024-01-01 12:00:00', '2024-01-02 16:00:00')
      ON CONFLICT DO NOTHING
    `);

    console.log('✅ Database tables created matching loader structure');
  } catch (error) {
    console.warn('Could not create test database tables:', error.message);
  }

  console.log("🔧 Global test setup complete");
};