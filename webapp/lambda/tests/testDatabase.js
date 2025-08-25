const { newDb } = require("pg-mem");

// Create in-memory PostgreSQL database for testing
const createTestDatabase = () => {
  const db = newDb();

  // Create test schema
  db.public.none(`
    CREATE TABLE user_portfolio (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      symbol VARCHAR(10) NOT NULL,
      quantity REAL NOT NULL DEFAULT 0,
      avg_cost REAL NOT NULL DEFAULT 0,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE user_api_keys (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      provider VARCHAR(50) NOT NULL,
      encrypted_data TEXT,
      user_salt TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      last_used TIMESTAMP DEFAULT NULL,
      UNIQUE(user_id, provider)
    );

    CREATE TABLE stock_prices (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      price REAL NOT NULL,
      change_amount REAL DEFAULT 0,
      change_percent REAL DEFAULT 0,
      volume INTEGER DEFAULT 0,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE price_daily (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL,
      date DATE NOT NULL,
      open_price REAL,
      high_price REAL, 
      low_price REAL,
      close_price REAL,
      adj_close_price REAL,
      volume BIGINT,
      change_amount REAL,
      change_percent REAL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE risk_alerts (
      id VARCHAR(50) PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      alert_type VARCHAR(50) NOT NULL,
      message TEXT,
      severity VARCHAR(20) DEFAULT 'medium',
      status VARCHAR(20) DEFAULT 'active',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      acknowledged_at TIMESTAMP NULL
    );

    CREATE TABLE market_data (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      price REAL NOT NULL,
      current_price REAL,
      previous_close REAL,
      volume INTEGER DEFAULT 0,
      change_percent REAL DEFAULT 0,
      market_cap BIGINT DEFAULT 0,
      date DATE DEFAULT CURRENT_DATE,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE market_indices (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      name VARCHAR(100) NOT NULL,
      value REAL NOT NULL,
      current_price REAL,
      previous_close REAL,
      change_percent REAL DEFAULT 0,
      date DATE DEFAULT CURRENT_DATE,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE sectors (
      id SERIAL PRIMARY KEY,
      sector VARCHAR(100) NOT NULL,
      stock_count INTEGER DEFAULT 0,
      avg_change REAL DEFAULT 0,
      total_volume BIGINT DEFAULT 0,
      avg_market_cap BIGINT DEFAULT 0,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE fear_greed_index (
      id SERIAL PRIMARY KEY,
      value INTEGER NOT NULL,
      value_text VARCHAR(50),
      classification VARCHAR(50),
      date DATE DEFAULT CURRENT_DATE,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE sentiment_indicators (
      id SERIAL PRIMARY KEY,
      indicator_type VARCHAR(50) NOT NULL,
      value REAL NOT NULL,
      metadata TEXT,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE watchlists (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      name VARCHAR(100) NOT NULL,
      description TEXT,
      is_default BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE watchlist_items (
      id SERIAL PRIMARY KEY,
      watchlist_id INTEGER NOT NULL,
      symbol VARCHAR(10) NOT NULL,
      added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      notes TEXT
    );

    CREATE TABLE portfolio_holdings (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      symbol VARCHAR(20) NOT NULL,
      quantity REAL NOT NULL DEFAULT 0,
      avg_price REAL NOT NULL DEFAULT 0,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE stock_symbols (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL UNIQUE,
      company_name VARCHAR(200) NOT NULL,
      sector VARCHAR(100),
      industry VARCHAR(150),
      market_cap BIGINT,
      pe_ratio REAL,
      is_active BOOLEAN DEFAULT TRUE,
      exchange VARCHAR(50),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Financial statement tables for financials route testing
    CREATE TABLE annual_income_statement (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(200) NOT NULL,
      value NUMERIC(20,2),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE annual_balance_sheet (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(200) NOT NULL,
      value NUMERIC(20,2),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE annual_cash_flow (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(200) NOT NULL,
      value NUMERIC(20,2),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE key_metrics (
      id SERIAL PRIMARY KEY,
      ticker VARCHAR(20) NOT NULL,
      date DATE NOT NULL,
      revenue NUMERIC(20,2),
      net_income NUMERIC(20,2),
      eps NUMERIC(10,4),
      pe_ratio NUMERIC(10,4),
      roe NUMERIC(10,4),
      roa NUMERIC(10,4),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE earnings_history (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL,
      report_date DATE NOT NULL,
      period VARCHAR(20),
      eps_estimate NUMERIC(10,4),
      eps_actual NUMERIC(10,4),
      surprise_percent NUMERIC(10,4),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Additional tables for test coverage
    CREATE TABLE backtest_results (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      strategy_name VARCHAR(200) NOT NULL,
      symbol VARCHAR(20) NOT NULL,
      start_date DATE NOT NULL,
      end_date DATE NOT NULL,
      initial_capital NUMERIC(20,2),
      final_value NUMERIC(20,2),
      total_return NUMERIC(10,4),
      max_drawdown NUMERIC(10,4),
      sharpe_ratio NUMERIC(10,4),
      win_rate NUMERIC(10,4),
      total_trades INTEGER,
      avg_trade_duration NUMERIC(10,2),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id, strategy_name, symbol, start_date, end_date)
    );

    CREATE TABLE price_history (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL,
      date DATE NOT NULL,
      timeframe VARCHAR(10) NOT NULL DEFAULT '1d',
      open NUMERIC(20,4),
      high NUMERIC(20,4),
      low NUMERIC(20,4),
      close NUMERIC(20,4),
      volume BIGINT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, timeframe)
    );

    CREATE TABLE risk_metrics (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      date DATE NOT NULL,
      portfolio_value NUMERIC(20,2),
      var_1d NUMERIC(20,2),
      var_30d NUMERIC(20,2),
      beta NUMERIC(10,4),
      alpha NUMERIC(10,4),
      sharpe_ratio NUMERIC(10,4),
      sortino_ratio NUMERIC(10,4),
      max_drawdown NUMERIC(10,4),
      volatility NUMERIC(10,4),
      correlation_spy NUMERIC(10,4),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id, date)
    );
  `);

  const adapter = db.adapters.createPg();

  // pg-mem returns an object with Pool and Client, we need to create a client
  const client = new adapter.Client();
  
  // Store the original query method
  const originalQuery = client.query.bind(client);
  
  // Create a wrapper that ensures connection
  client.query = async (text, params = []) => {
    try {
      await client.connect();
    } catch (e) {
      // Ignore if already connected
    }
    const result = await originalQuery(text, params);
    return result;
  };
  
  return client;
};

module.exports = { createTestDatabase };
