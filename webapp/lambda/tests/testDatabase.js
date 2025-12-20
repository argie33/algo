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
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Price daily table (exact match to setup_database_with_real_data.py but REAL instead of DOUBLE PRECISION)
    CREATE TABLE price_daily (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      open_price REAL,
      high_price REAL,
      low_price REAL,
      close_price REAL,
      adj_close_price REAL,
      volume BIGINT,
      change_amount REAL,
      change_percent REAL,
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date)
    );

    -- ETF price daily table (exact match to loadpricedaily.py but REAL instead of DOUBLE PRECISION)
    CREATE TABLE etf_price_daily (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      open REAL,
      high REAL,
      low REAL,
      close REAL,
      adj_close REAL,
      volume BIGINT,
      dividends REAL,
      stock_splits REAL,
      fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );


    -- Company profile table (exact match to loadinfo.py structure)
    CREATE TABLE company_profile (
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
      quote_source_name VARCHAR(100),
      custom_price_alert_confidence VARCHAR(20),
      address1 VARCHAR(200),
      city VARCHAR(100),
      state VARCHAR(50),
      postal_code VARCHAR(20),
      country VARCHAR(100),
      phone_number VARCHAR(50),
      website_url VARCHAR(200),
      ir_website_url VARCHAR(200),
      message_board_id VARCHAR(100),
      corporate_actions JSONB,
      sector VARCHAR(100),
      sector_key VARCHAR(100),
      sector_disp VARCHAR(100),
      industry VARCHAR(100),
      industry_key VARCHAR(100),
      industry_disp VARCHAR(100),
      business_summary TEXT,
      employee_count INT,
      first_trade_date_ms BIGINT,
      gmt_offset_ms BIGINT,
      exchange VARCHAR(20),
      full_exchange_name VARCHAR(100),
      exchange_timezone_name VARCHAR(100),
      exchange_timezone_short_name VARCHAR(20),
      exchange_data_delayed_by_sec INT,
      post_market_time_ms BIGINT,
      regular_market_time_ms BIGINT
    );

    -- Last updated tracking table (from loaders)
    CREATE TABLE last_updated (
      script_name VARCHAR(255) PRIMARY KEY,
      last_run TIMESTAMP WITH TIME ZONE
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
      ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
      previous_close REAL,
      regular_market_previous_close REAL,
      open_price REAL,
      regular_market_open REAL,
      day_low REAL,
      regular_market_day_low REAL,
      day_high REAL,
      regular_market_day_high REAL,
      regular_market_price REAL,
      current_price REAL,
      post_market_price REAL,
      post_market_change REAL,
      post_market_change_pct REAL,
      volume BIGINT,
      regular_market_volume BIGINT,
      average_volume BIGINT,
      avg_volume_10d BIGINT,
      avg_daily_volume_10d BIGINT,
      avg_daily_volume_3m BIGINT,
      bid_price REAL,
      ask_price REAL,
      bid_size INT,
      ask_size INT,
      market_state VARCHAR(20),
      fifty_two_week_low REAL,
      fifty_two_week_high REAL,
      fifty_two_week_range VARCHAR(50),
      fifty_two_week_low_change REAL,
      fifty_two_week_low_change_pct REAL,
      fifty_two_week_high_change REAL,
      fifty_two_week_high_change_pct REAL,
      fifty_two_week_change_pct REAL,
      fifty_day_avg REAL,
      two_hundred_day_avg REAL,
      fifty_day_avg_change REAL,
      fifty_day_avg_change_pct REAL,
      two_hundred_day_avg_change REAL,
      two_hundred_day_avg_change_pct REAL,
      source_interval_sec INT,
      market_cap BIGINT
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
      average_cost REAL DEFAULT 0,
      current_price REAL DEFAULT 0,
      market_value REAL DEFAULT 0,
      cost_basis REAL DEFAULT 0,
      pnl REAL DEFAULT 0,
      pnl_percent REAL DEFAULT 0,
      day_change REAL DEFAULT 0,
      day_change_percent REAL DEFAULT 0,
      weight REAL DEFAULT 0,
      sector VARCHAR(50),
      asset_class VARCHAR(20) DEFAULT 'equity',
      broker VARCHAR(50) DEFAULT 'manual',
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Stock symbols table (exact match to loadstocksymbols.py)
    CREATE TABLE stock_symbols (
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
    );

    -- ETF symbols table (exact match to loadstocksymbols.py)
    CREATE TABLE etf_symbols (
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
      ticker VARCHAR(10),
      year INTEGER,
      total_assets BIGINT,
      total_liabilities BIGINT,
      total_debt BIGINT,
      revenue BIGINT,
      net_income BIGINT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(ticker, year)
    );

    CREATE TABLE annual_cash_flow (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(20) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(200) NOT NULL,
      value NUMERIC(20,2),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Market data table (exact match to loadinfo.py but REAL for pg-mem compatibility)
    CREATE TABLE market_data (
      ticker VARCHAR(10) PRIMARY KEY,
      previous_close REAL,
      regular_market_previous_close REAL,
      open_price REAL,
      regular_market_open REAL,
      day_low REAL,
      regular_market_day_low REAL,
      day_high REAL,
      regular_market_day_high REAL,
      regular_market_price REAL,
      current_price REAL,
      post_market_price REAL,
      post_market_change REAL,
      post_market_change_pct REAL,
      volume BIGINT,
      regular_market_volume BIGINT,
      average_volume BIGINT,
      avg_volume_10d BIGINT,
      avg_daily_volume_10d BIGINT,
      avg_daily_volume_3m BIGINT,
      bid_price REAL,
      ask_price REAL,
      bid_size INT,
      ask_size INT,
      market_state VARCHAR(20),
      fifty_two_week_low REAL,
      fifty_two_week_high REAL,
      fifty_two_week_range VARCHAR(50),
      fifty_two_week_low_change REAL,
      fifty_two_week_low_change_pct REAL,
      fifty_two_week_high_change REAL,
      fifty_two_week_high_change_pct REAL,
      fifty_two_week_change_pct REAL,
      fifty_day_avg REAL,
      two_hundred_day_avg REAL,
      fifty_day_avg_change REAL,
      fifty_day_avg_change_pct REAL,
      two_hundred_day_avg_change REAL,
      two_hundred_day_avg_change_pct REAL,
      source_interval_sec INT,
      market_cap BIGINT
    );

    CREATE TABLE key_metrics (
      ticker VARCHAR(10) PRIMARY KEY,
      trailing_pe REAL,
      forward_pe REAL,
      price_to_sales_ttm REAL,
      price_to_book REAL,
      book_value REAL,
      peg_ratio REAL,
      enterprise_value BIGINT,
      ev_to_revenue REAL,
      ev_to_ebitda REAL,
      total_revenue BIGINT,
      net_income BIGINT,
      ebitda BIGINT,
      gross_profit BIGINT,
      eps_trailing REAL,
      eps_forward REAL,
      eps_current_year REAL,
      price_eps_current_year REAL,
      earnings_q_growth_pct REAL,
      earnings_ts_ms BIGINT,
      earnings_ts_start_ms BIGINT,
      earnings_ts_end_ms BIGINT,
      earnings_call_ts_start_ms BIGINT,
      earnings_call_ts_end_ms BIGINT,
      is_earnings_date_estimate BOOLEAN,
      total_cash BIGINT,
      cash_per_share REAL,
      operating_cashflow BIGINT,
      free_cashflow BIGINT,
      total_debt BIGINT,
      debt_to_equity REAL,
      quick_ratio REAL,
      current_ratio REAL,
      profit_margin_pct REAL,
      gross_margin_pct REAL,
      ebitda_margin_pct REAL,
      operating_margin_pct REAL,
      return_on_assets_pct REAL,
      return_on_equity_pct REAL,
      revenue_growth_pct REAL,
      earnings_growth_pct REAL,
      last_split_factor VARCHAR(20),
      last_split_date_ms BIGINT,
      dividend_rate REAL,
      dividend_yield REAL,
      five_year_avg_dividend_yield REAL,
      ex_dividend_date_ms BIGINT,
      last_annual_dividend_amt REAL,
      last_annual_dividend_yield REAL,
      last_dividend_amt REAL,
      last_dividend_date_ms BIGINT,
      dividend_date_ms BIGINT,
      payout_ratio REAL
    );

    -- Leadership team table (from loadinfo.py)
    CREATE TABLE leadership_team (
      ticker VARCHAR(10) NOT NULL,
      person_name VARCHAR(200) NOT NULL,
      age INT,
      title VARCHAR(200),
      birth_year INT,
      fiscal_year INT,
      total_pay REAL,
      exercised_value REAL,
      unexercised_value REAL,
      role_source VARCHAR(50),
      PRIMARY KEY(ticker, person_name, role_source)
    );

    -- Governance scores table (from loadinfo.py)
    CREATE TABLE governance_scores (
      ticker VARCHAR(10) PRIMARY KEY,
      audit_risk INT,
      board_risk INT,
      compensation_risk INT,
      shareholder_rights_risk INT,
      overall_risk INT,
      governance_epoch_ms BIGINT,
      comp_data_as_of_ms BIGINT
    );

    -- Analyst estimates table (from loadinfo.py)
    CREATE TABLE analyst_estimates (
      ticker VARCHAR(10) PRIMARY KEY,
      target_high_price REAL,
      target_low_price REAL,
      target_mean_price REAL,
      target_median_price REAL,
      recommendation_key VARCHAR(50),
      recommendation_mean REAL,
      analyst_opinion_count INT,
      average_analyst_rating REAL
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

    -- Buy Sell tables (exact match to loadbuyselldaily.py, loadbuysellweekly.py, loadbuysellmonthly.py)
    CREATE TABLE buy_sell_daily (
      id           SERIAL PRIMARY KEY,
      symbol       VARCHAR(20)    NOT NULL,
      timeframe    VARCHAR(10)    NOT NULL,
      date         DATE           NOT NULL,
      open         REAL,
      high         REAL,
      low          REAL,
      close        REAL,
      volume       BIGINT,
      signal       VARCHAR(10),
      buylevel     REAL,
      stoplevel    REAL,
      inposition   BOOLEAN,
      UNIQUE(symbol, timeframe, date)
    );

    CREATE TABLE buy_sell_weekly (
      id           SERIAL PRIMARY KEY,
      symbol       VARCHAR(20)    NOT NULL,
      timeframe    VARCHAR(10)    NOT NULL,
      date         DATE           NOT NULL,
      open         REAL,
      high         REAL,
      low          REAL,
      close        REAL,
      volume       BIGINT,
      signal       VARCHAR(10),
      buylevel     REAL,
      stoplevel    REAL,
      inposition   BOOLEAN,
      UNIQUE(symbol, timeframe, date)
    );

    CREATE TABLE buy_sell_monthly (
      id           SERIAL PRIMARY KEY,
      symbol       VARCHAR(20)    NOT NULL,
      timeframe    VARCHAR(10)    NOT NULL,
      date         DATE           NOT NULL,
      open         REAL,
      high         REAL,
      low          REAL,
      close        REAL,
      volume       BIGINT,
      signal       VARCHAR(10),
      buylevel     REAL,
      stoplevel    REAL,
      inposition   BOOLEAN,
      UNIQUE(symbol, timeframe, date)
    );

    -- Indexes for performance (matching loaders)
    CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
    CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol_date ON etf_price_daily(symbol, date);
    CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol_date ON buy_sell_daily(symbol, date);
    CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_symbol_date ON buy_sell_weekly(symbol, date);
    CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_symbol_date ON buy_sell_monthly(symbol, date);

    -- Sample data for core tables (matching yfinance structure from loaders)
    INSERT INTO company_profile (ticker, short_name, long_name, quote_type, sector, market, currency, exchange, business_summary) VALUES
    ('AAPL', 'Apple Inc.', 'Apple Inc.', 'EQUITY', 'Technology', 'us_market', 'USD', 'NMS', 'Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.'),
    ('GOOGL', 'Alphabet Inc.', 'Alphabet Inc. (Class A)', 'EQUITY', 'Communication Services', 'us_market', 'USD', 'NMS', 'Alphabet Inc. provides search and advertising services.'),
    ('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'EQUITY', 'Technology', 'us_market', 'USD', 'NMS', 'Microsoft Corporation develops, licenses, and supports software, services, devices, and solutions worldwide.'),
    ('TSLA', 'Tesla, Inc.', 'Tesla, Inc.', 'EQUITY', 'Consumer Cyclical', 'us_market', 'USD', 'NMS', 'Tesla, Inc. designs, develops, manufactures, leases, and sells electric vehicles.');

    INSERT INTO market_data (ticker, name, date, price, volume, market_cap, fifty_two_week_high, fifty_two_week_low) VALUES
    ('AAPL', 'Apple Inc.', '2024-01-02', 152.0, 50000000, 2400000000000, 199.62, 124.17),
    ('GOOGL', 'Alphabet Inc.', '2024-01-02', 2820.0, 25000000, 1800000000000, 3030.93, 2193.62),
    ('MSFT', 'Microsoft Corporation', '2024-01-02', 382.0, 30000000, 2800000000000, 468.35, 309.45),
    ('TSLA', 'Tesla Inc.', '2024-01-02', 240.0, 80000000, 780000000000, 414.50, 138.80);

    INSERT INTO key_metrics (ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book, debt_to_equity, current_ratio, quick_ratio, dividend_yield, peg_ratio, total_revenue, net_income) VALUES
    ('AAPL', 28.5, 26.2, 7.8, 45.2, 1.73, 0.98, 0.81, 0.0044, 2.1, 394328000000, 96995000000),
    ('GOOGL', 22.8, 20.5, 5.2, 4.2, 0.12, 2.8, 2.6, 0.0, 1.8, 307394000000, 76033000000),
    ('MSFT', 35.4, 28.9, 12.1, 13.8, 0.31, 2.5, 2.0, 0.0073, 2.4, 211915000000, 72361000000),
    ('TSLA', 75.2, 58.3, 8.9, 12.1, 0.18, 1.3, 1.1, 0.0, 3.2, 96773000000, 15000000000);

    INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, volume) VALUES
    ('AAPL', '2024-01-15', 150.0, 155.0, 148.0, 152.0, 50000000),
    ('AAPL', '2024-01-16', 152.0, 158.0, 150.0, 157.0, 55000000),
    ('GOOGL', '2024-01-15', 2800.0, 2850.0, 2780.0, 2820.0, 25000000),
    ('GOOGL', '2024-01-16', 2820.0, 2880.0, 2810.0, 2850.0, 28000000),
    ('MSFT', '2024-01-15', 380.0, 385.0, 375.0, 382.0, 30000000),
    ('MSFT', '2024-01-16', 382.0, 390.0, 378.0, 385.0, 32000000),
    ('TSLA', '2024-01-15', 238.0, 245.0, 235.0, 240.0, 80000000),
    ('TSLA', '2024-01-16', 240.0, 248.0, 238.0, 245.0, 85000000);

    -- Sample data for buy_sell tables (for testing)
    INSERT INTO buy_sell_daily (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
    ('AAPL', 'Daily', '2024-01-15', 150.0, 155.0, 148.0, 152.0, 1000000, 'Buy', 155.0, 145.0, true),
    ('AAPL', 'Daily', '2024-01-16', 152.0, 158.0, 150.0, 157.0, 1200000, 'None', 160.0, 145.0, true),
    ('GOOGL', 'Daily', '2024-01-15', 2800.0, 2850.0, 2780.0, 2820.0, 500000, 'Buy', 2850.0, 2750.0, true),
    ('MSFT', 'Daily', '2024-01-15', 380.0, 385.0, 375.0, 382.0, 800000, 'Sell', 390.0, 370.0, false);

    INSERT INTO buy_sell_weekly (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
    ('AAPL', 'Weekly', '2024-01-15', 150.0, 160.0, 145.0, 157.0, 5000000, 'Buy', 160.0, 140.0, true),
    ('GOOGL', 'Weekly', '2024-01-15', 2800.0, 2900.0, 2750.0, 2850.0, 2500000, 'Buy', 2900.0, 2700.0, true);

    INSERT INTO buy_sell_monthly (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
    ('AAPL', 'Monthly', '2024-01-01', 145.0, 165.0, 140.0, 157.0, 20000000, 'Buy', 165.0, 135.0, true),
    ('GOOGL', 'Monthly', '2024-01-01', 2750.0, 2950.0, 2700.0, 2850.0, 10000000, 'Buy', 2950.0, 2650.0, true);
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
