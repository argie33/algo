// Global setup for tests - creates ONLY webapp-specific tables
// Python loaders handle their own table creation
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

    console.log('🔧 Global Setup: Creating tables from setup_test_database.sql...');

    // Run the webapp-specific database setup SQL file
    // Python loaders create their own tables in AWS/production
    const fs = require('fs');
    const path = require('path');

    try {
      const setupSqlPath = path.join(__dirname, '../../setup_test_database.sql');
      const setupSql = fs.readFileSync(setupSqlPath, 'utf8');

      // Split SQL into individual statements and execute them
      const statements = setupSql.split(';').filter(stmt => stmt.trim().length > 0);

      for (const statement of statements) {
        if (statement.trim()) {
          await query(statement.trim() + ';');
        }
      }

      console.log('✅ Database schema loaded from setup_test_database.sql');
    } catch (error) {
      console.warn('⚠️  Could not load setup_test_database.sql, using fallback table creation:', error.message);

      // Fallback: Create essential webapp tables only

      // Watchlists (user-specific feature)
    await query(`
      CREATE TABLE IF NOT EXISTS watchlists (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        name VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS watchlist_items (
        id SERIAL PRIMARY KEY,
        watchlist_id INTEGER REFERENCES watchlists(id) ON DELETE CASCADE,
        symbol VARCHAR(10) NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(watchlist_id, symbol)
      )
    `);

    // Portfolio (user-specific feature)
    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_holdings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,8) NOT NULL,
        average_cost DECIMAL(10,4) NOT NULL,
        current_price DECIMAL(10,4),
        market_value DECIMAL(15,2),
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, symbol)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_performance (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        date DATE NOT NULL,
        total_value DECIMAL(15,2),
        daily_pnl DECIMAL(15,2),
        total_pnl DECIMAL(15,2),
        total_pnl_percent DECIMAL(8,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, date)
      )
    `);

    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_metadata (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        broker VARCHAR(100) NOT NULL DEFAULT 'paper',
        total_value DECIMAL(15,2),
        total_cash DECIMAL(15,2),
        total_pnl DECIMAL(15,2),
        total_pnl_percent DECIMAL(8,4),
        day_pnl DECIMAL(15,2),
        day_pnl_percent DECIMAL(8,4),
        positions_count INTEGER DEFAULT 0,
        account_status VARCHAR(50) DEFAULT 'active',
        environment VARCHAR(20) DEFAULT 'paper',
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, broker)
      )
    `);

    // Orders (user-specific trading feature)
    await query(`
      CREATE TABLE IF NOT EXISTS orders_paper (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
        quantity DECIMAL(15,8) NOT NULL,
        order_type VARCHAR(20) NOT NULL DEFAULT 'market',
        price DECIMAL(10,4),
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        executed_at TIMESTAMP,
        executed_price DECIMAL(10,4)
      )
    `);

    // User alerts (webapp-specific feature)
    await query(`
      CREATE TABLE IF NOT EXISTS user_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        alert_type VARCHAR(50) NOT NULL,
        condition_type VARCHAR(20) NOT NULL,
        threshold_value DECIMAL(10,4),
        message TEXT,
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        triggered_at TIMESTAMP
      )
    `);

    // Insert minimal test data for webapp tables
    await query(`
      INSERT INTO watchlists (user_id, name) VALUES
      ('test-user-123', 'My Watchlist'),
      ('test-user-456', 'Tech Stocks')
      ON CONFLICT DO NOTHING
    `);

    await query(`
      INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value) VALUES
      ('test-user-123', 'AAPL', 10.0, 150.00, 175.50, 1755.00),
      ('test-user-123', 'MSFT', 5.0, 300.00, 420.75, 2103.75)
      ON CONFLICT (user_id, symbol) DO NOTHING
    `);

      // Add core Python loader tables for fallback
      await query(`
        DROP TABLE IF EXISTS buy_sell_daily CASCADE
      `);
      await query(`
        DROP TABLE IF EXISTS buy_sell_weekly CASCADE
      `);
      await query(`
        DROP TABLE IF EXISTS buy_sell_monthly CASCADE
      `);
      await query(`
        DROP TABLE IF EXISTS company_profile CASCADE
      `);

      // Create buy_sell tables with correct schema
      await query(`
        CREATE TABLE buy_sell_daily (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(20) NOT NULL,
          timeframe VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          open REAL,
          high REAL,
          low REAL,
          close REAL,
          volume BIGINT,
          signal VARCHAR(10),
          buylevel REAL,
          stoplevel REAL,
          inposition BOOLEAN,
          UNIQUE(symbol, timeframe, date)
        )
      `);

      await query(`
        CREATE TABLE buy_sell_weekly (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(20) NOT NULL,
          timeframe VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          open REAL,
          high REAL,
          low REAL,
          close REAL,
          volume BIGINT,
          signal VARCHAR(10),
          buylevel REAL,
          stoplevel REAL,
          inposition BOOLEAN,
          UNIQUE(symbol, timeframe, date)
        )
      `);

      await query(`
        CREATE TABLE buy_sell_monthly (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(20) NOT NULL,
          timeframe VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          open REAL,
          high REAL,
          low REAL,
          close REAL,
          volume BIGINT,
          signal VARCHAR(10),
          buylevel REAL,
          stoplevel REAL,
          inposition BOOLEAN,
          UNIQUE(symbol, timeframe, date)
        )
      `);

      await query(`
        CREATE TABLE company_profile (
          ticker VARCHAR(10) PRIMARY KEY,
          short_name VARCHAR(100),
          long_name VARCHAR(200),
          display_name VARCHAR(200),
          quote_type VARCHAR(50),
          symbol_type VARCHAR(50),
          exchange_name VARCHAR(100),
          sector VARCHAR(100),
          industry VARCHAR(100)
        )
      `);

      await query(`
        DROP TABLE IF EXISTS market_data CASCADE
      `);

      await query(`
        CREATE TABLE market_data (
          ticker VARCHAR(10) PRIMARY KEY,
          symbol VARCHAR(10),
          previous_close NUMERIC,
          regular_market_previous_close NUMERIC,
          regular_market_price NUMERIC,
          current_price NUMERIC,
          volume BIGINT,
          regular_market_volume BIGINT,
          market_cap BIGINT
        )
      `);

      await query(`
        DROP TABLE IF EXISTS key_metrics CASCADE
      `);

      await query(`
        CREATE TABLE key_metrics (
          ticker VARCHAR(10) PRIMARY KEY,
          trailing_pe NUMERIC,
          forward_pe NUMERIC,
          price_to_sales_ttm NUMERIC,
          price_to_book NUMERIC,
          peg_ratio NUMERIC,
          enterprise_value BIGINT,
          profit_margin_pct NUMERIC,
          return_on_assets_pct NUMERIC,
          return_on_equity_pct NUMERIC,
          dividend_yield NUMERIC,
          eps_trailing NUMERIC,
          eps_forward NUMERIC,
          total_revenue NUMERIC,
          net_income NUMERIC,
          debt_to_equity NUMERIC,
          current_ratio NUMERIC,
          quick_ratio NUMERIC,
          total_cash NUMERIC,
          cash_per_share NUMERIC,
          operating_cashflow NUMERIC,
          free_cashflow NUMERIC,
          beta NUMERIC,
          earnings_growth_pct NUMERIC,
          revenue_growth_pct NUMERIC
        )
      `);

      await query(`
        CREATE TABLE IF NOT EXISTS price_daily (
          symbol VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          open DECIMAL(10,4),
          high DECIMAL(10,4),
          low DECIMAL(10,4),
          close DECIMAL(10,4),
          adj_close DECIMAL(10,4),
          volume BIGINT,
          PRIMARY KEY(symbol, date)
        )
      `);

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

      // Add test data
      await query(`
        INSERT INTO company_profile (ticker, short_name, long_name, display_name, quote_type, symbol_type, exchange_name, sector, industry) VALUES
        ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Apple Inc.', 'EQUITY', 'EQUITY', 'NASDAQ', 'Technology', 'Consumer Electronics'),
        ('MSFT', 'Microsoft Corp.', 'Microsoft Corporation', 'Microsoft Corporation', 'EQUITY', 'EQUITY', 'NASDAQ', 'Technology', 'Software'),
        ('GOOGL', 'Alphabet Inc.', 'Alphabet Inc.', 'Alphabet Inc.', 'EQUITY', 'EQUITY', 'NASDAQ', 'Technology', 'Internet Content & Information'),
        ('TSLA', 'Tesla Inc.', 'Tesla, Inc.', 'Tesla, Inc.', 'EQUITY', 'EQUITY', 'NASDAQ', 'Consumer Cyclical', 'Auto Manufacturers'),
        ('AMZN', 'Amazon.com Inc.', 'Amazon.com, Inc.', 'Amazon.com, Inc.', 'EQUITY', 'EQUITY', 'NASDAQ', 'Consumer Cyclical', 'Internet Retail')
        ON CONFLICT (ticker) DO NOTHING
      `);

      await query(`
        INSERT INTO market_data (ticker, symbol, previous_close, regular_market_previous_close, regular_market_price, current_price, volume, regular_market_volume, market_cap) VALUES
        ('AAPL', 'AAPL', 175.50, 175.50, 180.25, 180.25, 52000000, 52000000, 2800000000000),
        ('MSFT', 'MSFT', 420.75, 420.75, 425.30, 425.30, 28000000, 28000000, 3100000000000),
        ('GOOGL', 'GOOGL', 135.80, 135.80, 138.45, 138.45, 31000000, 31000000, 1700000000000),
        ('TSLA', 'TSLA', 250.30, 250.30, 255.75, 255.75, 67000000, 67000000, 800000000000),
        ('AMZN', 'AMZN', 145.20, 145.20, 148.90, 148.90, 35000000, 35000000, 1500000000000)
        ON CONFLICT (ticker) DO NOTHING
      `);

      await query(`
        INSERT INTO key_metrics (ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book, peg_ratio, enterprise_value, profit_margin_pct, return_on_assets_pct, return_on_equity_pct, dividend_yield, eps_trailing, eps_forward, total_revenue, net_income, debt_to_equity, current_ratio, quick_ratio, total_cash, cash_per_share, operating_cashflow, free_cashflow, beta, earnings_growth_pct, revenue_growth_pct) VALUES
        ('AAPL', 28.5, 25.2, 7.1, 4.2, 2.1, 2750000000000, 0.26, 0.18, 0.35, 0.55, 6.15, 7.20, 394328000000, 99803000000, 1.73, 1.12, 1.00, 29965000000, 1.85, 99584000000, 84726000000, 1.29, 0.085, 0.071),
        ('MSFT', 32.1, 28.8, 8.2, 5.1, 2.5, 3050000000000, 0.31, 0.15, 0.42, 0.80, 11.75, 13.50, 245122000000, 88136000000, 0.35, 2.52, 2.19, 104757000000, 14.05, 87582000000, 65149000000, 0.89, 0.103, 0.099),
        ('GOOGL', 22.3, 20.1, 4.5, 3.8, 1.8, 1680000000000, 0.21, 0.12, 0.28, 0.00, 5.89, 6.75, 307394000000, 73795000000, 0.12, 2.05, 1.87, 115696000000, 8.89, 91495000000, 67012000000, 1.05, 0.126, 0.089),
        ('TSLA', 45.2, 38.5, 9.1, 8.9, 3.2, 780000000000, 0.08, 0.09, 0.18, 0.00, 4.73, 6.20, 96773000000, 15000000000, 0.17, 1.54, 1.27, 26801000000, 8.54, 13256000000, 7563000000, 2.05, 0.192, 0.151),
        ('AMZN', 38.7, 35.2, 2.1, 6.2, 2.8, 1480000000000, 0.05, 0.06, 0.12, 0.00, 0.94, 1.25, 574785000000, 30425000000, 0.34, 1.09, 0.87, 88916000000, 8.67, 84946000000, 35574000000, 1.15, 0.089, 0.124)
        ON CONFLICT (ticker) DO NOTHING
      `);

      await query(`
        INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate, eps_difference, surprise_percent) VALUES
        ('AAPL', '2024-01-15', 2.18, 2.10, 0.08, 3.81),
        ('MSFT', '2024-01-20', 2.93, 2.87, 0.06, 2.09),
        ('GOOGL', '2024-01-25', 1.64, 1.59, 0.05, 3.14),
        ('TSLA', '2024-01-30', 0.71, 0.73, -0.02, -2.74),
        ('AMZN', '2024-02-05', 1.00, 0.80, 0.20, 25.00)
        ON CONFLICT (symbol, quarter) DO NOTHING
      `);

      // Add test data for buy_sell tables
      await query(`
        INSERT INTO buy_sell_daily (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
        ('AAPL', 'daily', '2024-01-15', 175.00, 180.00, 174.50, 179.25, 50000000, 'BUY', 178.00, 172.00, true),
        ('MSFT', 'daily', '2024-01-15', 420.00, 425.00, 418.75, 423.50, 25000000, 'HOLD', 422.00, 415.00, false),
        ('GOOGL', 'daily', '2024-01-15', 135.50, 139.00, 134.25, 137.75, 30000000, 'SELL', 136.00, 140.00, false),
        ('TSLA', 'daily', '2024-01-15', 250.00, 255.50, 248.75, 252.25, 60000000, 'BUY', 253.00, 245.00, true),
        ('AMZN', 'daily', '2024-01-15', 145.00, 149.25, 143.50, 147.75, 35000000, 'HOLD', 148.00, 142.00, false)
        ON CONFLICT (symbol, timeframe, date) DO NOTHING
      `);

      await query(`
        INSERT INTO buy_sell_weekly (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
        ('AAPL', 'weekly', '2024-01-15', 170.00, 185.00, 168.50, 179.25, 250000000, 'BUY', 180.00, 165.00, true),
        ('MSFT', 'weekly', '2024-01-15', 415.00, 430.00, 410.00, 423.50, 125000000, 'HOLD', 425.00, 405.00, false)
        ON CONFLICT (symbol, timeframe, date) DO NOTHING
      `);

      await query(`
        INSERT INTO buy_sell_monthly (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
        ('AAPL', 'monthly', '2024-01-01', 160.00, 190.00, 155.00, 179.25, 1000000000, 'BUY', 185.00, 150.00, true)
        ON CONFLICT (symbol, timeframe, date) DO NOTHING
      `);

      // Add ETF tables for tests
      await query(`
        DROP TABLE IF EXISTS etfs CASCADE
      `);
      await query(`
        DROP TABLE IF EXISTS etf_holdings CASCADE
      `);

      await query(`
        CREATE TABLE etfs (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) UNIQUE NOT NULL,
          fund_name VARCHAR(200),
          total_assets BIGINT,
          expense_ratio DECIMAL(5,4),
          dividend_yield DECIMAL(5,2),
          inception_date DATE,
          category VARCHAR(100)
        )
      `);

      await query(`
        CREATE TABLE etf_holdings (
          id SERIAL PRIMARY KEY,
          etf_symbol VARCHAR(10) NOT NULL,
          holding_symbol VARCHAR(10) NOT NULL,
          company_name VARCHAR(200),
          weight_percent DECIMAL(5,2),
          shares_held BIGINT,
          market_value BIGINT,
          sector VARCHAR(100),
          UNIQUE(etf_symbol, holding_symbol)
        )
      `);

      // Add ETF test data
      await query(`
        INSERT INTO etfs (symbol, fund_name, total_assets, expense_ratio, dividend_yield) VALUES
        ('SPY', 'SPDR S&P 500 ETF Trust', 350000000000, 0.0945, 1.25),
        ('QQQ', 'Invesco QQQ Trust', 150000000000, 0.20, 0.65),
        ('VTI', 'Vanguard Total Stock Market ETF', 250000000000, 0.03, 1.8)
        ON CONFLICT (symbol) DO NOTHING
      `);

      await query(`
        INSERT INTO etf_holdings (etf_symbol, holding_symbol, company_name, weight_percent, shares_held, market_value, sector) VALUES
        ('SPY', 'AAPL', 'Apple Inc.', 6.85, 165000000, 25000000000, 'Technology'),
        ('SPY', 'MSFT', 'Microsoft Corp.', 6.12, 72000000, 21000000000, 'Technology'),
        ('SPY', 'GOOGL', 'Alphabet Inc.', 4.25, 12000000, 14500000000, 'Technology'),
        ('SPY', 'TSLA', 'Tesla Inc.', 2.8, 55000000, 9800000000, 'Consumer Cyclical'),
        ('SPY', 'AMZN', 'Amazon.com Inc.', 3.15, 65000000, 10500000000, 'Consumer Cyclical')
        ON CONFLICT (etf_symbol, holding_symbol) DO NOTHING
      `);

      // Add sentiment analysis tables
      await query(`
        DROP TABLE IF EXISTS analyst_sentiment_analysis CASCADE
      `);
      await query(`
        DROP TABLE IF EXISTS social_sentiment_analysis CASCADE
      `);

      await query(`
        CREATE TABLE analyst_sentiment_analysis (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(20) NOT NULL,
          date DATE NOT NULL,
          recommendation_mean NUMERIC,
          price_target_vs_current NUMERIC,
          analyst_count INTEGER,
          UNIQUE(symbol, date)
        )
      `);

      await query(`
        CREATE TABLE social_sentiment_analysis (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(20) NOT NULL,
          date DATE NOT NULL,
          news_sentiment_score NUMERIC,
          reddit_sentiment_score NUMERIC,
          search_volume_index INTEGER,
          news_article_count INTEGER,
          UNIQUE(symbol, date)
        )
      `);

      // Add sentiment test data with recent dates
      await query(`
        INSERT INTO analyst_sentiment_analysis (symbol, date, recommendation_mean, price_target_vs_current, analyst_count) VALUES
        ('AAPL', CURRENT_DATE, 2.1, 5.5, 25),
        ('AAPL', CURRENT_DATE - 1, 2.0, 4.8, 24),
        ('AAPL', CURRENT_DATE - 2, 2.2, 6.2, 26),
        ('MSFT', CURRENT_DATE, 1.9, 8.2, 22),
        ('GOOGL', CURRENT_DATE, 2.0, 12.1, 18),
        ('TSLA', CURRENT_DATE, 2.5, -2.8, 15),
        ('AMZN', CURRENT_DATE, 2.2, 7.3, 20)
        ON CONFLICT (symbol, date) DO NOTHING
      `);

      await query(`
        INSERT INTO social_sentiment_analysis (symbol, date, news_sentiment_score, reddit_sentiment_score, search_volume_index, news_article_count) VALUES
        ('AAPL', CURRENT_DATE, 0.75, 0.68, 85, 152),
        ('AAPL', CURRENT_DATE - 1, 0.72, 0.65, 82, 148),
        ('AAPL', CURRENT_DATE - 2, 0.78, 0.71, 88, 156),
        ('MSFT', CURRENT_DATE, 0.82, 0.71, 78, 134),
        ('GOOGL', CURRENT_DATE, 0.71, 0.64, 92, 167),
        ('TSLA', CURRENT_DATE, 0.45, 0.52, 125, 289),
        ('AMZN', CURRENT_DATE, 0.78, 0.73, 88, 198)
        ON CONFLICT (symbol, date) DO NOTHING
      `);

      console.log('✅ Global Setup: Webapp-only tables created successfully (fallback)');
    }

  } catch (error) {
    console.error('❌ Global setup failed:', error);
    // Don't throw - allow tests to continue and fail gracefully if needed
  }
};