// Load environment variables first
require('dotenv').config();

// Database setup for individual test files
const { query, initializeDatabase } = require('../../utils/database');

// Helper to check if database is available for tests
async function isDatabaseAvailable() {
  try {
    const result = await query('SELECT 1 as test');
    return result !== null && result.rows && result.rows.length > 0;
  } catch (error) {
    return false;
  }
}

// Helper to get test data from real database
async function getTestData(tableName, limit = 10) {
  try {
    const result = await query(`SELECT * FROM ${tableName} LIMIT $1`, [limit]);
    return result?.rows || [];
  } catch (error) {
    console.warn(`Could not fetch test data from ${tableName}:`, error.message);
    return [];
  }
}

// Helper to create test data if needed
async function ensureTestData() {
  try {
    console.log('🔧 Setting up loader table structures...');

    // Ensure core loader tables exist (matching loadinfo.py structure)
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

    await query(`
      CREATE TABLE IF NOT EXISTS stock_symbols (
        symbol VARCHAR(10) PRIMARY KEY,
        name VARCHAR(200),
        sector VARCHAR(100),
        market VARCHAR(50),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS market_data (
        symbol VARCHAR(20),
        name VARCHAR(255),
        date DATE,
        price DECIMAL(12,4),
        volume BIGINT,
        market_cap BIGINT,
        return_1d DECIMAL(8,6),
        return_5d DECIMAL(8,6),
        return_1m DECIMAL(8,6),
        return_3m DECIMAL(8,6),
        return_6m DECIMAL(8,6),
        return_1y DECIMAL(8,6),
        volatility_30d DECIMAL(8,6),
        volatility_90d DECIMAL(8,6),
        volatility_1y DECIMAL(8,6),
        sma_20 DECIMAL(12,4),
        sma_50 DECIMAL(12,4),
        sma_200 DECIMAL(12,4),
        price_vs_sma_20 DECIMAL(8,6),
        price_vs_sma_50 DECIMAL(8,6),
        price_vs_sma_200 DECIMAL(8,6),
        high_52w DECIMAL(12,4),
        low_52w DECIMAL(12,4),
        distance_from_high DECIMAL(8,6),
        distance_from_low DECIMAL(8,6),
        avg_volume_30d BIGINT,
        volume_ratio DECIMAL(8,4),
        beta DECIMAL(8,4),
        asset_class VARCHAR(50),
        region VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    // Create comprehensive key_metrics table matching reset-database-to-loaders.sql
    await query(`
      CREATE TABLE IF NOT EXISTS key_metrics (
        ticker VARCHAR(10) PRIMARY KEY,
        trailing_pe NUMERIC,
        forward_pe NUMERIC,
        price_to_sales_ttm NUMERIC,
        price_to_book NUMERIC,
        book_value NUMERIC,
        peg_ratio NUMERIC,
        enterprise_value BIGINT,
        ev_to_revenue NUMERIC,
        ev_to_ebitda NUMERIC,
        total_revenue BIGINT,
        net_income BIGINT,
        ebitda BIGINT,
        gross_profit BIGINT,
        eps_trailing NUMERIC,
        eps_forward NUMERIC,
        eps_current_year NUMERIC,
        price_eps_current_year NUMERIC,
        earnings_q_growth_pct NUMERIC,
        revenue_growth_pct NUMERIC,
        earnings_growth_pct NUMERIC,
        total_cash BIGINT,
        cash_per_share NUMERIC,
        operating_cashflow BIGINT,
        free_cashflow BIGINT,
        total_debt BIGINT,
        debt_to_equity NUMERIC,
        quick_ratio NUMERIC,
        current_ratio NUMERIC,
        profit_margin_pct NUMERIC,
        gross_margin_pct NUMERIC,
        ebitda_margin_pct NUMERIC,
        operating_margin_pct NUMERIC,
        return_on_assets_pct NUMERIC,
        return_on_equity_pct NUMERIC,
        dividend_rate NUMERIC,
        dividend_yield NUMERIC,
        five_year_avg_dividend_yield NUMERIC,
        last_annual_dividend_amt NUMERIC,
        last_annual_dividend_yield NUMERIC
      )
    `);

    // Insert comprehensive test data for key_metrics
    await query(`
      INSERT INTO key_metrics (
        ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book,
        peg_ratio, enterprise_value, total_revenue, net_income, ebitda,
        eps_trailing, eps_forward, dividend_yield, debt_to_equity,
        current_ratio, profit_margin_pct, gross_margin_pct,
        return_on_equity_pct, return_on_assets_pct
      ) VALUES
      ('AAPL', 28.5, 26.2, 7.8, 45.2, 2.1, 3500000000000, 365000000000, 94000000000, 120000000000, 5.89, 6.25, 0.52, 1.73, 1.07, 25.7, 43.0, 175.0, 27.1),
      ('MSFT', 32.1, 29.8, 12.4, 13.5, 2.5, 2800000000000, 211000000000, 72000000000, 88000000000, 10.95, 12.10, 0.68, 0.47, 2.54, 34.2, 68.4, 47.1, 18.3),
      ('GOOGL', 24.7, 22.3, 5.2, 5.8, 1.8, 1700000000000, 283000000000, 76000000000, 92000000000, 5.02, 5.85, 0.0, 0.10, 3.77, 26.9, 57.0, 29.8, 16.2)
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS price_daily (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        adj_close DOUBLE PRECISION,
        volume BIGINT,
        dividends DOUBLE PRECISION,
        stock_splits DOUBLE PRECISION,
        change_percent DOUBLE PRECISION,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Add unique constraint separately to handle existing tables
    // Check if constraint already exists before trying to add it
    const constraintExists = await query(`
      SELECT COUNT(*) FROM pg_constraint
      WHERE conname = 'unique_symbol_date'
    `);

    if (constraintExists.rows[0].count === '0') {
      try {
        await query(`
          ALTER TABLE price_daily
          ADD CONSTRAINT unique_symbol_date
          UNIQUE (symbol, date)
        `);
      } catch (error) {
        // Only log if it's an unexpected error
        if (!error.message.includes('already exists') && error.code !== '42P07') {
          console.warn('Could not add unique constraint to price_daily:', error.message);
        }
      }
    }

    await query(`
      CREATE TABLE IF NOT EXISTS stock_scores (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        fundamental_score DECIMAL(5,2),
        technical_score DECIMAL(5,2),
        overall_score DECIMAL(5,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    // Create buy_sell tables matching loadlatestbuyselldaily.py structure
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

    // Ensure technical_data_daily table exists for signals route
    await query(`
      CREATE TABLE IF NOT EXISTS technical_data_daily (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        rsi DECIMAL(5,2),
        macd DECIMAL(10,6),
        bb_upper DECIMAL(12,4),
        bb_lower DECIMAL(12,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    // Insert basic test data for major symbols
    await query(`
      INSERT INTO company_profile (ticker, short_name, long_name, sector, industry, currency) VALUES
      ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics', 'USD'),
      ('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'Technology', 'Software', 'USD')
      ON CONFLICT (ticker) DO NOTHING
    `);

    // Insert stock symbols if they don't exist
    const symbolExists = await query(`SELECT COUNT(*) FROM stock_symbols WHERE symbol IN ('AAPL', 'MSFT')`);
    if (symbolExists && symbolExists.rows && symbolExists.rows[0].count < 2) {
      await query(`
        INSERT INTO stock_symbols (symbol, security_name)
        SELECT 'AAPL', 'Apple Inc.' WHERE NOT EXISTS (SELECT 1 FROM stock_symbols WHERE symbol = 'AAPL')
        UNION ALL
        SELECT 'MSFT', 'Microsoft Corporation' WHERE NOT EXISTS (SELECT 1 FROM stock_symbols WHERE symbol = 'MSFT')
      `);
    }

    // Ensure company_profile records exist before inserting market_data
    await query(`
      INSERT INTO company_profile (ticker, short_name, long_name, sector, industry) VALUES
      ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics'),
      ('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'Technology', 'Software'),
      ('SPY', 'SPDR S&P 500 ETF Trust', 'SPDR S&P 500 ETF Trust', 'ETF', 'ETF'),
      ('QQQ', 'Invesco QQQ Trust', 'Invesco QQQ Trust', 'ETF', 'ETF')
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      INSERT INTO market_data (symbol, name, date, price, volume, market_cap) VALUES
      ('AAPL', 'Apple Inc.', '2024-01-02', 150.25, 65000000, 3500000000000),
      ('MSFT', 'Microsoft Corporation', '2024-01-02', 350.75, 45000000, 2800000000000),
      ('SPY', 'SPDR S&P 500 ETF Trust', '2024-01-02', 446.95, 65000000, 400000000000),
      ('QQQ', 'Invesco QQQ Trust', '2024-01-02', 387.30, 42000000, 200000000000)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    // fundamental_metrics data insertion removed - using actual loader tables instead

    await query(`
      INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume) VALUES
      ('AAPL', '2024-01-02', 149.50, 151.25, 148.75, 150.25, 150.25, 65000000),
      ('AAPL', '2024-01-01', 148.00, 150.50, 147.50, 149.50, 149.50, 58000000),
      ('MSFT', '2024-01-02', 348.25, 352.50, 347.00, 350.75, 350.75, 45000000),
      ('MSFT', '2024-01-01', 346.50, 349.25, 345.75, 348.25, 348.25, 42000000),
      ('GOOGL', '2024-01-02', 139.75, 142.50, 138.25, 141.80, 141.80, 28000000),
      ('GOOGL', '2024-01-01', 137.50, 140.25, 136.75, 139.75, 139.75, 25000000)
      ON CONFLICT DO NOTHING
    `);

    await query(`
      INSERT INTO stock_scores (symbol, date, fundamental_score, technical_score, overall_score) VALUES
      ('AAPL', '2024-01-02', 85.5, 72.3, 78.9),
      ('MSFT', '2024-01-02', 88.2, 75.6, 81.9)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    // Buy_sell_daily test data is already handled by globalSetup.js - no duplicate insert needed

    // Technical data already inserted by globalSetup.js - no duplicate insert needed

    // Create earnings_history table for financial routes
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

    await query(`
      INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate, surprise_percent) VALUES
      ('AAPL', '2024-01-01', 2.18, 2.10, 3.8),
      ('MSFT', '2024-01-01', 2.93, 2.88, 1.7)
      ON CONFLICT (symbol, quarter) DO NOTHING
    `);

    // Create portfolio_metadata table for portfolio routes
    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_metadata (
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
    await query(`
      CREATE TABLE IF NOT EXISTS technical_alerts (
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

    // Create ETFs table (from etf.js requirements)
    await query(`
      CREATE TABLE IF NOT EXISTS etfs (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL UNIQUE,
        fund_name VARCHAR(255),
        total_assets DECIMAL(20,2),
        expense_ratio DECIMAL(6,4),
        dividend_yield DECIMAL(8,6),
        inception_date DATE,
        category VARCHAR(100),
        strategy TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create ETF holdings table (from etf.js requirements)
    await query(`
      CREATE TABLE IF NOT EXISTS etf_holdings (
        id SERIAL PRIMARY KEY,
        etf_symbol VARCHAR(10) NOT NULL,
        holding_symbol VARCHAR(10) NOT NULL,
        company_name VARCHAR(255),
        weight_percent DECIMAL(8,6),
        shares_held BIGINT,
        market_value DECIMAL(15,2),
        sector VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio returns table (from performance.js requirements)
    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_returns (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        calculation_type VARCHAR(50) NOT NULL,
        period VARCHAR(20) NOT NULL,
        time_weighted_return DECIMAL(10,6),
        dollar_weighted_return DECIMAL(10,6),
        annualized_time_weighted DECIMAL(10,6),
        annualized_dollar_weighted DECIMAL(10,6),
        excess_return DECIMAL(10,6),
        calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio risk metrics table (from performance.js and risk.js requirements)
    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_risk_metrics (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        portfolio_id INTEGER,
        period VARCHAR(20) NOT NULL,
        volatility DECIMAL(10,6),
        var_95 DECIMAL(10,6),
        var_99 DECIMAL(10,6),
        expected_shortfall_95 DECIMAL(10,6),
        expected_shortfall_99 DECIMAL(10,6),
        maximum_drawdown DECIMAL(10,6),
        calmar_ratio DECIMAL(10,6),
        beta DECIMAL(10,6),
        correlation_to_market DECIMAL(10,6),
        tracking_error DECIMAL(10,6),
        active_risk DECIMAL(10,6),
        systematic_risk DECIMAL(10,6),
        idiosyncratic_risk DECIMAL(10,6),
        concentration_risk DECIMAL(10,6),
        liquidity_risk DECIMAL(10,6),
        calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
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
      ON CONFLICT DO NOTHING
    `);

    // Create trades table for trading functionality
    await query(`DROP TABLE IF EXISTS trades`);
    await query(`
      CREATE TABLE trades (
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

    await query(`
      INSERT INTO trades (trade_id, user_id, symbol, side, quantity, type, status, executed_at, average_fill_price, filled_quantity) VALUES
      ('trade-1', 'test-user-1', 'AAPL', 'buy', 100, 'market', 'filled', '2024-01-01', 150.50, 100),
      ('trade-2', 'test-user-2', 'MSFT', 'sell', 50, 'limit', 'filled', '2024-01-02', 330.25, 50)
      ON CONFLICT DO NOTHING
    `);

    // Create news alerts table for alerts routes
    await query(`
      CREATE TABLE IF NOT EXISTS news_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        sentiment_threshold DECIMAL(5,4),
        sentiment_type VARCHAR(20),
        sources JSONB,
        notification_methods JSONB,
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio alerts table for alerts routes
    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        alert_type VARCHAR(50) NOT NULL,
        threshold_value DECIMAL(12,4),
        condition VARCHAR(20),
        notification_methods JSONB,
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio transactions table for trade analytics
    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_transactions (
        transaction_id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
        transaction_type VARCHAR(20) NOT NULL,
        quantity NUMERIC NOT NULL,
        price NUMERIC NOT NULL,
        amount NUMERIC NOT NULL,
        commission NUMERIC DEFAULT 0,
        pnl NUMERIC DEFAULT 0,
        transaction_date DATE NOT NULL,
        settlement_date DATE,
        description TEXT,
        account_id VARCHAR(100),
        broker VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create order activities table for order execution tracking
    await query(`
      CREATE TABLE IF NOT EXISTS order_activities (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        order_id INTEGER NOT NULL,
        activity_type VARCHAR(50) NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio_performance table
    await query(`DROP TABLE IF EXISTS portfolio_performance`);
    await query(`
      CREATE TABLE portfolio_performance (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        total_value DECIMAL(15,4) NOT NULL,
        daily_pnl DECIMAL(15,4) DEFAULT 0,
        daily_pnl_percent DECIMAL(8,4) DEFAULT 0,
        total_pnl DECIMAL(15,4) DEFAULT 0,
        total_pnl_percent DECIMAL(8,4) DEFAULT 0,
        date DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio_holdings table
    await query(`DROP TABLE IF EXISTS portfolio_holdings`);
    await query(`
      CREATE TABLE portfolio_holdings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,4) NOT NULL,
        average_cost DECIMAL(12,4) NOT NULL,
        current_price DECIMAL(12,4) DEFAULT 0,
        market_value DECIMAL(15,4) DEFAULT 0,
        unrealized_pnl DECIMAL(15,4) DEFAULT 0,
        unrealized_pnl_percent DECIMAL(8,4) DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio_symbol_performance table
    await query(`DROP TABLE IF EXISTS portfolio_symbol_performance`);
    await query(`
      CREATE TABLE portfolio_symbol_performance (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        realized_pnl DECIMAL(15,4) DEFAULT 0,
        unrealized_pnl DECIMAL(15,4) DEFAULT 0,
        win_rate DECIMAL(8,4) DEFAULT 0,
        avg_hold_time_days INTEGER DEFAULT 0,
        period VARCHAR(10) NOT NULL,
        calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio_analytics table
    await query(`DROP TABLE IF EXISTS portfolio_analytics`);
    await query(`
      CREATE TABLE portfolio_analytics (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        period VARCHAR(10) NOT NULL,
        total_return DECIMAL(8,4) DEFAULT 0,
        sharpe_ratio DECIMAL(8,4) DEFAULT 0,
        max_drawdown DECIMAL(8,4) DEFAULT 0,
        volatility DECIMAL(8,4) DEFAULT 0,
        beta DECIMAL(8,4) DEFAULT 1.0,
        alpha DECIMAL(8,4) DEFAULT 0,
        tracking_error DECIMAL(8,4) DEFAULT 0,
        information_ratio DECIMAL(8,4) DEFAULT 0,
        sortino_ratio DECIMAL(8,4) DEFAULT 0,
        calmar_ratio DECIMAL(8,4) DEFAULT 0,
        win_rate DECIMAL(8,4) DEFAULT 0,
        average_win DECIMAL(8,4) DEFAULT 0,
        average_loss DECIMAL(8,4) DEFAULT 0,
        profit_factor DECIMAL(8,4) DEFAULT 0,
        recovery_factor DECIMAL(8,4) DEFAULT 0,
        calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create trade_history table
    await query(`DROP TABLE IF EXISTS trade_history`);
    await query(`
      CREATE TABLE trade_history (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        action VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,4) NOT NULL,
        price DECIMAL(12,4) NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        order_id VARCHAR(50),
        commission DECIMAL(10,4) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create attribution_analysis table
    await query(`DROP TABLE IF EXISTS attribution_analysis`);
    await query(`
      CREATE TABLE attribution_analysis (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        period VARCHAR(20) NOT NULL,
        total_return DECIMAL(8,4),
        benchmark_return DECIMAL(8,4),
        active_return DECIMAL(8,4),
        allocation_effect DECIMAL(8,4),
        selection_effect DECIMAL(8,4),
        interaction_effect DECIMAL(8,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create brinson_attribution table
    await query(`DROP TABLE IF EXISTS brinson_attribution`);
    await query(`
      CREATE TABLE brinson_attribution (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        sector VARCHAR(50) NOT NULL,
        allocation_effect DECIMAL(8,4),
        selection_effect DECIMAL(8,4),
        interaction_effect DECIMAL(8,4),
        total_effect DECIMAL(8,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create attribution_components table
    await query(`DROP TABLE IF EXISTS attribution_components`);
    await query(`
      CREATE TABLE attribution_components (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        component_type VARCHAR(50) NOT NULL,
        component_name VARCHAR(100) NOT NULL,
        weight DECIMAL(8,4),
        return_value DECIMAL(8,4),
        contribution DECIMAL(8,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create analyst_sentiment_analysis table
    await query(`DROP TABLE IF EXISTS analyst_sentiment_analysis`);
    await query(`
      CREATE TABLE analyst_sentiment_analysis (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        sentiment_score DECIMAL(5,2) DEFAULT 0,
        sentiment_label VARCHAR(20) DEFAULT 'neutral',
        confidence DECIMAL(5,2) DEFAULT 0,
        analysis_date DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create analyst_recommendations table
    await query(`DROP TABLE IF EXISTS analyst_recommendations`);
    await query(`
      CREATE TABLE analyst_recommendations (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        analyst_firm VARCHAR(100),
        recommendation VARCHAR(20) NOT NULL,
        previous_recommendation VARCHAR(20),
        target_price DECIMAL(12,4),
        previous_target_price DECIMAL(12,4),
        date_published DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create analyst_coverage table
    await query(`DROP TABLE IF EXISTS analyst_coverage`);
    await query(`
      CREATE TABLE analyst_coverage (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        analyst_firm VARCHAR(100) NOT NULL,
        analyst_name VARCHAR(100),
        coverage_started DATE,
        coverage_status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create analyst_price_targets table
    await query(`DROP TABLE IF EXISTS analyst_price_targets`);
    await query(`
      CREATE TABLE analyst_price_targets (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        analyst_firm VARCHAR(100),
        target_price DECIMAL(12,4) NOT NULL,
        previous_target_price DECIMAL(12,4),
        target_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create research_reports table
    await query(`DROP TABLE IF EXISTS research_reports`);
    await query(`
      CREATE TABLE research_reports (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        analyst_firm VARCHAR(100),
        report_title VARCHAR(200),
        report_summary TEXT,
        report_url VARCHAR(500),
        report_date DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create position_history table for trades route
    await query(`DROP TABLE IF EXISTS position_history`);
    await query(`
      CREATE TABLE position_history (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        side VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,4) NOT NULL,
        avg_entry_price DECIMAL(12,4),
        avg_exit_price DECIMAL(12,4),
        net_pnl DECIMAL(15,4),
        gross_pnl DECIMAL(15,4),
        return_percentage DECIMAL(8,4),
        holding_period_days INTEGER,
        opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at TIMESTAMP,
        status VARCHAR(20) DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO position_history (user_id, symbol, side, quantity, avg_entry_price, avg_exit_price, net_pnl, return_percentage, status, opened_at, closed_at) VALUES
      ('test-user-1', 'AAPL', 'long', 100, 150.25, 155.75, 550.00, 3.66, 'closed', '2024-01-01 10:00:00', '2024-01-02 15:30:00'),
      ('test-user-2', 'MSFT', 'long', 50, 348.25, 352.50, 212.50, 1.22, 'closed', '2024-01-01 11:00:00', '2024-01-02 14:00:00'),
      ('test-user-1', 'GOOGL', 'long', 25, 2850.00, NULL, 393.75, 0.55, 'open', '2024-01-02 09:30:00', NULL),
      ('test-user-2', 'TSLA', 'short', 75, 247.80, 244.25, 266.25, 1.43, 'closed', '2024-01-01 12:00:00', '2024-01-02 16:00:00')
      ON CONFLICT DO NOTHING
    `);

    // Create broker_api_configs table (from trades.js requirements)
    await query(`DROP TABLE IF EXISTS broker_api_configs`);
    await query(`
      CREATE TABLE broker_api_configs (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        broker VARCHAR(50) NOT NULL,
        is_active BOOLEAN DEFAULT true,
        last_sync_status VARCHAR(50) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO broker_api_configs (user_id, broker, is_active, last_sync_status) VALUES
      ('test-user-123', 'alpaca', true, 'connected'),
      ('test-user-1', 'alpaca', true, 'connected'),
      ('test-user-2', 'td_ameritrade', false, 'pending')
      ON CONFLICT DO NOTHING
    `);

    // Create user_api_keys table (from trades.js requirements)
    await query(`DROP TABLE IF EXISTS user_api_keys`);
    await query(`
      CREATE TABLE user_api_keys (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        broker_name VARCHAR(50) NOT NULL,
        encrypted_api_key TEXT,
        key_iv TEXT,
        key_auth_tag TEXT,
        encrypted_api_secret TEXT,
        secret_iv TEXT,
        secret_auth_tag TEXT,
        is_sandbox BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO user_api_keys (user_id, broker_name, encrypted_api_key, encrypted_api_secret, is_sandbox) VALUES
      ('test-user-123', 'alpaca', 'encrypted_key_123', 'encrypted_secret_123', true),
      ('test-user-1', 'alpaca', 'encrypted_key_456', 'encrypted_secret_456', true),
      ('test-user-2', 'td_ameritrade', 'encrypted_key_789', 'encrypted_secret_789', true)
      ON CONFLICT DO NOTHING
    `);

    // Create earnings_reports table (from calendar.js requirements)
    await query(`DROP TABLE IF EXISTS earnings_reports`);
    await query(`
      CREATE TABLE earnings_reports (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        report_date DATE,
        quarter INTEGER,
        year INTEGER,
        eps_estimate DECIMAL(10,4),
        eps_actual DECIMAL(10,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      INSERT INTO earnings_reports (symbol, report_date, quarter, year, eps_estimate, eps_actual) VALUES
      ('AAPL', '2024-01-15', 1, 2024, 1.85, 1.92),
      ('MSFT', '2024-01-20', 1, 2024, 2.45, 2.51),
      ('GOOGL', '2024-01-25', 1, 2024, 3.25, 3.18),
      ('TSLA', '2024-01-30', 1, 2024, 0.85, 0.91)
      ON CONFLICT DO NOTHING
    `);

    // Add test tables for performance stress testing
    await query(`DROP TABLE IF EXISTS test_transaction_stress`);
    await query(`
      CREATE TABLE test_transaction_stress (
        id SERIAL PRIMARY KEY,
        value INTEGER NOT NULL,
        updated_by VARCHAR(50),
        transaction_id VARCHAR(50),
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`DROP TABLE IF EXISTS test_isolation_stress`);
    await query(`
      CREATE TABLE test_isolation_stress (
        id INTEGER PRIMARY KEY,
        counter INTEGER DEFAULT 0,
        last_updated_by INTEGER
      )
    `);

    // Economic Data table (from loadecondata.py)
    await query(`DROP TABLE IF EXISTS economic_data`);
    await query(`
      CREATE TABLE economic_data (
        id SERIAL PRIMARY KEY,
        series_id VARCHAR(100) NOT NULL,
        date DATE NOT NULL,
        value DOUBLE PRECISION,
        category VARCHAR(100),
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(series_id, date)
      )
    `);

    // Custom signals table (for signals routes)
    await query(`
      CREATE TABLE IF NOT EXISTS custom_signals (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        signal_type VARCHAR(50) NOT NULL,
        signal_strength DECIMAL(5,2),
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        is_active BOOLEAN DEFAULT true
      )
    `);

    // Create watchlist tables for watchlist routes
    await query(`
      CREATE TABLE IF NOT EXISTS watchlists (
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
      CREATE TABLE IF NOT EXISTS watchlist_items (
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
      ON CONFLICT DO NOTHING
    `);

    await query(`
      INSERT INTO watchlist_items (watchlist_id, symbol, notes) VALUES
      (1, 'AAPL', 'Apple Inc'),
      (1, 'MSFT', 'Microsoft'),
      (2, 'GOOGL', 'Google/Alphabet')
      ON CONFLICT (watchlist_id, symbol) DO NOTHING
    `);

    console.log('✅ Basic test data and loader tables created');
  } catch (error) {
    console.warn('Could not create test data:', error.message);
  }
}

// Make helpers globally available for tests
global.testDbHelpers = {
  isDatabaseAvailable,
  getTestData,
  ensureTestData,
  query: async (sql, params) => {
    try {
      return await query(sql, params);
    } catch (error) {
      console.warn('Test query failed:', error.message);
      return null;
    }
  }
};

// Setup hook to run before all tests
beforeAll(async () => {
  if (await isDatabaseAvailable()) {
    await ensureTestData();
    console.log('✅ Database is available for tests');
  } else {
    console.warn('⚠️ Database not available - tests will use graceful fallback');
  }
});