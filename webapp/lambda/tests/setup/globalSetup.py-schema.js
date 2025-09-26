// Global setup for tests - ensures database tables match Python loader schemas EXACTLY
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

    console.log('🔧 Setting up database tables to match Python loader schemas EXACTLY...');

    // Create stock_symbols table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS stock_symbols CASCADE`);
    await query(`
      CREATE TABLE stock_symbols (
        symbol VARCHAR(50) PRIMARY KEY,
        name TEXT,
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

    // Create price_daily table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS price_daily CASCADE`);
    await query(`
      CREATE TABLE price_daily (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open_price DOUBLE PRECISION,
        high_price DOUBLE PRECISION,
        low_price DOUBLE PRECISION,
        close_price DOUBLE PRECISION,
        adj_close_price DOUBLE PRECISION,
        volume BIGINT,
        change_amount DOUBLE PRECISION,
        change_percent DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date)
      )
    `);

    // Create technical_data_daily table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS technical_data_daily CASCADE`);
    await query(`
      CREATE TABLE technical_data_daily (
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
        sma_100 DOUBLE PRECISION,
        sma_200 DOUBLE PRECISION,
        ema_10 DOUBLE PRECISION,
        ema_20 DOUBLE PRECISION,
        ema_50 DOUBLE PRECISION,
        ema_100 DOUBLE PRECISION,
        ema_200 DOUBLE PRECISION,
        bb_upper DOUBLE PRECISION,
        bb_middle DOUBLE PRECISION,
        bb_lower DOUBLE PRECISION,
        stoch_k DOUBLE PRECISION,
        stoch_d DOUBLE PRECISION,
        williams_r DOUBLE PRECISION,
        cci DOUBLE PRECISION,
        ppo DOUBLE PRECISION,
        ultimate_osc DOUBLE PRECISION,
        trix DOUBLE PRECISION,
        dpo DOUBLE PRECISION,
        kama DOUBLE PRECISION,
        tema DOUBLE PRECISION,
        aroon_up DOUBLE PRECISION,
        aroon_down DOUBLE PRECISION,
        aroon_osc DOUBLE PRECISION,
        bop DOUBLE PRECISION,
        cmo DOUBLE PRECISION,
        dx DOUBLE PRECISION,
        minus_dm DOUBLE PRECISION,
        plus_dm DOUBLE PRECISION,
        willr DOUBLE PRECISION,
        natr DOUBLE PRECISION,
        trange DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create stocks table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS stocks CASCADE`);
    await query(`
      CREATE TABLE stocks (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL UNIQUE,
        name VARCHAR(255),
        sector VARCHAR(100),
        industry VARCHAR(100),
        market_cap NUMERIC,
        price NUMERIC,
        dividend_yield NUMERIC,
        beta NUMERIC,
        exchange VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create analyst_recommendations table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS analyst_recommendations CASCADE`);
    await query(`
      CREATE TABLE analyst_recommendations (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        analyst_firm VARCHAR(100),
        rating VARCHAR(20),
        target_price DOUBLE PRECISION,
        current_price DOUBLE PRECISION,
        date_published DATE,
        date_updated DATE DEFAULT CURRENT_DATE,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Create portfolio_holdings table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS portfolio_holdings CASCADE`);
    await query(`
      CREATE TABLE portfolio_holdings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        quantity NUMERIC NOT NULL DEFAULT 0,
        average_cost NUMERIC NOT NULL DEFAULT 0,
        current_price NUMERIC DEFAULT 0,
        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, symbol)
      )
    `);

    // Create portfolio_performance table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS portfolio_performance CASCADE`);
    await query(`
      CREATE TABLE portfolio_performance (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        date DATE NOT NULL,
        total_value NUMERIC NOT NULL DEFAULT 0,
        daily_pnl NUMERIC DEFAULT 0,
        total_pnl NUMERIC DEFAULT 0,
        total_pnl_percent NUMERIC DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, date)
      )
    `);

    // Create economic_data table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS economic_data CASCADE`);
    await query(`
      CREATE TABLE economic_data (
        series_id TEXT NOT NULL,
        date DATE NOT NULL,
        value DOUBLE PRECISION,
        title TEXT,
        units TEXT,
        frequency TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (series_id, date)
      )
    `);

    // Create api_keys table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS api_keys CASCADE`);
    await query(`
      CREATE TABLE api_keys (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        provider VARCHAR(100) NOT NULL,
        api_key VARCHAR(500) NOT NULL,
        api_secret VARCHAR(500),
        is_sandbox BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, provider)
      )
    `);

    // Create trading_strategies table exactly matching Python setup_database_with_real_data.py
    await query(`DROP TABLE IF EXISTS trading_strategies CASCADE`);
    await query(`
      CREATE TABLE trading_strategies (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255),
        strategy_name VARCHAR(255) NOT NULL,
        strategy_type VARCHAR(50) NOT NULL,
        description TEXT,
        strategy_description TEXT,
        strategy_code TEXT,
        backtest_id VARCHAR(255),
        risk_settings JSONB,
        hft_config JSONB,
        deployment_status VARCHAR(50) DEFAULT 'draft',
        parameters JSONB DEFAULT '{}',
        status VARCHAR(20) DEFAULT 'active',
        performance_metrics JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Insert test data matching Python schema
    await query(`
      INSERT INTO stock_symbols (symbol, name, exchange, security_name) VALUES
      ('AAPL', 'Apple Inc.', 'NASDAQ', 'Apple Inc.'),
      ('MSFT', 'Microsoft Corporation', 'NASDAQ', 'Microsoft Corporation'),
      ('GOOGL', 'Alphabet Inc.', 'NASDAQ', 'Alphabet Inc. (Class A)')
      ON CONFLICT (symbol) DO NOTHING
    `);

    await query(`
      INSERT INTO stocks (symbol, name, sector, industry, market_cap, price, exchange) VALUES
      ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3400000000000, 180.50, 'NASDAQ'),
      ('MSFT', 'Microsoft Corporation', 'Technology', 'Software Infrastructure', 2800000000000, 415.25, 'NASDAQ'),
      ('GOOGL', 'Alphabet Inc.', 'Communication Services', 'Internet Content & Information', 1680000000000, 142.80, 'NASDAQ')
      ON CONFLICT (symbol) DO NOTHING
    `);

    await query(`
      INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, volume) VALUES
      ('AAPL', '2024-01-02', 180.00, 181.50, 179.50, 180.50, 65000000),
      ('MSFT', '2024-01-02', 414.00, 416.25, 413.50, 415.25, 32000000),
      ('GOOGL', '2024-01-02', 142.00, 143.80, 141.50, 142.80, 28000000)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    await query(`
      INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price) VALUES
      ('test-user-1', 'AAPL', 100, 175.00, 180.50),
      ('test-user-1', 'MSFT', 50, 400.00, 415.25),
      ('test-user-1', 'GOOGL', 75, 140.00, 142.80)
      ON CONFLICT (user_id, symbol) DO NOTHING
    `);

    console.log('✅ Database tables created matching Python loader structure');
    return true;

  } catch (error) {
    console.error('❌ Error setting up database tables:', error);
    throw error;
  }
};