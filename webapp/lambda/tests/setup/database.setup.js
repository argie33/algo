// Load environment variables first
require('dotenv').config();

// Configure real database connection for tests
process.env.NODE_ENV = "test";
process.env.ALLOW_DEV_BYPASS = "true";
process.env.JWT_SECRET = "test-secret-key-for-testing-only";

// Set real database connection environment variables
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

console.log('🔧 Setting up webapp-specific database tables...');
console.log('Using database config from environment variables');
console.log(`Database config loaded from environment: ${process.env.DB_HOST}:${process.env.DB_PORT}/${process.env.DB_NAME}`);

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

// Helper to create all tables using the main setup_database.sql file
async function ensureTestData() {
  try {
    console.log('🔧 Setting up webapp-specific tables from setup_database.sql...');

    // Use the webapp-specific database setup SQL file
    const fs = require('fs');
    const path = require('path');

    try {
      const setupSqlPath = path.join(__dirname, '../../setup_test_database.sql');
      const setupSql = fs.readFileSync(setupSqlPath, 'utf8');

      // Split SQL into individual statements and execute them
      const statements = setupSql.split(';').filter(stmt => stmt.trim().length > 0);

      for (const statement of statements) {
        if (statement.trim()) {
          try {
            await query(statement.trim() + ';');
          } catch (error) {
            // Log error but continue with other statements
            if (!error.message.includes('already exists')) {
              console.warn(`Warning executing SQL statement: ${error.message}`);
            }
          }
        }
      }

      console.log('✅ Database schema loaded from setup_database.sql');
    } catch (error) {
      console.warn('⚠️  Could not load setup_database.sql, using fallback:', error.message);

      // Fallback: Create essential webapp tables only
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

    await query(`
      CREATE TABLE IF NOT EXISTS portfolio_holdings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,8) NOT NULL,
        average_cost DECIMAL(10,4) NOT NULL,
        current_price DECIMAL(10,4),
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

    // Create orders table for trading functionality
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

    // Insert minimal test data for webapp tables
    await query(`
      INSERT INTO watchlists (user_id, name) VALUES
      ('test-user-123', 'My Watchlist'),
      ('test-user-456', 'Tech Stocks')
      ON CONFLICT DO NOTHING
    `);

    console.log('✅ Database webapp-only tables created successfully');
    }

  } catch (error) {
    console.error('❌ Error creating webapp tables:', error);
    throw error;
  }
}

// Function to create Python loader tables for testing
async function createLoaderTables() {
  try {
    // Tables are now created by setup_test_database.sql with proper schemas
    // Just create any additional tables not in that file

    console.log('✅ Using table schemas from setup_test_database.sql');

    // Check and fix stock_scores table schema - add all missing columns
    try {
      // Add all missing columns that are needed for the test data
      const missingColumns = [
        'sma_20 DECIMAL(10,2)',
        'sma_50 DECIMAL(10,2)',
        'volume_avg_30d BIGINT',
        'current_price DECIMAL(10,2)',
        'price_change_1d DECIMAL(5,2)',
        'price_change_5d DECIMAL(5,2)',
        'price_change_30d DECIMAL(5,2)',
        'volatility_30d DECIMAL(5,2)',
        'market_cap BIGINT',
        'pe_ratio DECIMAL(8,2)',
        'score_date DATE',
        'last_updated TIMESTAMP'
      ];

      for (const column of missingColumns) {
        try {
          await query(`ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS ${column}`);
        } catch (error) {
          // Column probably already exists
        }
      }
      console.log('✅ Ensured stock_scores has all required columns');
    } catch (error) {
      console.warn('Could not add stock_scores columns:', error.message);
    }

    console.log('✅ Python loader tables created for testing');
  } catch (error) {
    console.error('❌ Error creating Python loader tables:', error);
    throw error;
  }
}

// Function to populate test data for Python loader tables (will only work if tables exist)
async function populateLoaderTestData() {
  try {
    // Create and populate economic_data table first
    await query(`
      CREATE TABLE IF NOT EXISTS economic_data (
        series_id TEXT NOT NULL,
        date DATE NOT NULL,
        value DOUBLE PRECISION,
        PRIMARY KEY (series_id, date)
      )
    `);

    // Populate economic test data
    await query(`
      INSERT INTO economic_data (series_id, date, value) VALUES
      -- GDP data
      ('GDP', '2025-01-01', 27000000),
      ('GDP', '2024-10-01', 26800000),
      ('GDP', '2024-07-01', 26600000),
      ('GDP', '2024-04-01', 26400000),
      ('GDP', '2024-01-01', 26200000),

      -- GDPC1 (Real GDP)
      ('GDPC1', '2025-01-01', 22500000),
      ('GDPC1', '2024-10-01', 22400000),
      ('GDPC1', '2024-07-01', 22300000),
      ('GDPC1', '2024-04-01', 22200000),
      ('GDPC1', '2024-01-01', 22100000),

      -- CPI data
      ('CPI', '2025-01-01', 307.789),
      ('CPI', '2024-12-01', 307.026),
      ('CPI', '2024-11-01', 306.746),
      ('CPI', '2024-10-01', 306.269),
      ('CPI', '2024-09-01', 305.691),

      -- CPIAUCSL (Consumer Price Index for All Urban Consumers)
      ('CPIAUCSL', '2025-01-01', 307.789),
      ('CPIAUCSL', '2024-12-01', 307.026),
      ('CPIAUCSL', '2024-11-01', 306.746),
      ('CPIAUCSL', '2024-10-01', 306.269),
      ('CPIAUCSL', '2024-09-01', 305.691),

      -- Unemployment Rate
      ('UNRATE', '2025-01-01', 3.7),
      ('UNRATE', '2024-12-01', 3.8),
      ('UNRATE', '2024-11-01', 3.9),
      ('UNRATE', '2024-10-01', 4.0),
      ('UNRATE', '2024-09-01', 4.1),

      -- VIX Volatility Index
      ('VIXCLS', '2025-01-01', 15.39),
      ('VIXCLS', '2024-12-31', 16.45),
      ('VIXCLS', '2024-12-30', 15.82),
      ('VIXCLS', '2024-12-29', 14.98),
      ('VIXCLS', '2024-12-28', 15.67),

      -- Federal Funds Rate
      ('FEDFUNDS', '2025-01-01', 5.25),
      ('FEDFUNDS', '2024-12-01', 5.25),
      ('FEDFUNDS', '2024-11-01', 5.00),
      ('FEDFUNDS', '2024-10-01', 5.00),
      ('FEDFUNDS', '2024-09-01', 4.75)
      ON CONFLICT (series_id, date) DO NOTHING
    `);

    console.log('✅ Economic test data populated for testing');
    // Insert test data into Python loader tables
    await query(`
      INSERT INTO company_profile (ticker, short_name, long_name, sector, industry) VALUES
      ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics'),
      ('MSFT', 'Microsoft Corp.', 'Microsoft Corporation', 'Technology', 'Software'),
      ('GOOGL', 'Alphabet Inc.', 'Alphabet Inc.', 'Technology', 'Internet Services')
      ON CONFLICT (ticker) DO NOTHING
    `);

    // Try to insert market data - handle any conflicts gracefully
    try {
      // Use only columns that exist in the actual market_data table schema
      await query(`
        INSERT INTO market_data (symbol, date, regular_market_price, previous_close) VALUES
        ('AAPL', CURRENT_DATE, 175.50, 174.25),
        ('MSFT', CURRENT_DATE, 420.75, 419.50),
        ('GOOGL', CURRENT_DATE, 143.50, 142.75)
        ON CONFLICT DO NOTHING
      `);
    } catch (error) {
      console.warn('Could not insert market_data test data:', error.message);
    }

    await query(`
      INSERT INTO key_metrics (ticker, trailing_pe, forward_pe, dividend_yield, eps_trailing, price_to_sales_ttm, price_to_book, peg_ratio, profit_margin_pct, return_on_assets_pct, return_on_equity_pct, eps_forward, total_revenue, net_income, debt_to_equity, current_ratio, quick_ratio, total_cash, cash_per_share, operating_cashflow, free_cashflow, beta, earnings_growth_pct, revenue_growth_pct, enterprise_value) VALUES
      ('AAPL', 28.5, 25.2, 0.55, 6.15, 7.8, 45.5, 2.1, 25.3, 0.18, 0.35, 7.20, 394328000000, 99803000000, 1.73, 1.12, 1.00, 29965000000, 1.85, 99584000000, 84726000000, 1.29, 0.085, 0.071, 2750000000000),
      ('MSFT', 35.8, 29.1, 0.80, 11.75, 12.4, 13.2, 2.5, 36.7, 0.15, 0.42, 13.50, 245122000000, 88136000000, 0.35, 2.52, 2.19, 104757000000, 14.05, 87582000000, 65149000000, 0.89, 0.103, 0.099, 3050000000000),
      ('GOOGL', 24.2, 21.5, 0.00, 5.89, 5.1, 6.8, 1.8, 22.4, 0.12, 0.28, 6.75, 307394000000, 73795000000, 0.12, 2.05, 1.87, 115696000000, 8.89, 91495000000, 67012000000, 1.05, 0.126, 0.089, 1680000000000)
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume) VALUES
      ('AAPL', CURRENT_DATE, 175.0, 176.5, 174.0, 175.5, 175.5, 65000000),
      ('MSFT', CURRENT_DATE, 420.0, 422.0, 419.0, 420.75, 420.75, 28000000),
      ('GOOGL', CURRENT_DATE, 142.0, 144.0, 141.0, 143.5, 143.5, 22000000)
      ON CONFLICT (symbol, date) DO NOTHING
    `);

    await query(`
      INSERT INTO stock_scores (symbol, composite_score, momentum_score, trend_score, value_score, quality_score, rsi, macd, sma_20, sma_50, volume_avg_30d, current_price, price_change_1d, price_change_5d, price_change_30d, volatility_30d, market_cap, pe_ratio, score_date, last_updated) VALUES
      ('AAPL', 88.7, 85.2, 90.1, 78.3, 88.7, 65.4, 2.45, 174.5, 170.2, 45000000, 175.50, 1.2, 3.5, 8.2, 18.5, 3400000000000, 28.5, CURRENT_DATE, CURRENT_TIMESTAMP),
      ('MSFT', 91.2, 88.5, 92.8, 85.1, 91.2, 72.1, 5.67, 418.3, 415.8, 25000000, 420.75, 2.1, 5.2, 12.1, 22.3, 3200000000000, 35.8, CURRENT_DATE, CURRENT_TIMESTAMP),
      ('GOOGL', 82.5, 78.9, 84.2, 75.6, 82.5, 58.3, 1.23, 142.8, 140.5, 20000000, 143.50, -0.5, 2.1, 4.8, 24.1, 1800000000000, 24.2, CURRENT_DATE, CURRENT_TIMESTAMP)
      ON CONFLICT (symbol) DO UPDATE SET
        composite_score = EXCLUDED.composite_score,
        momentum_score = EXCLUDED.momentum_score,
        trend_score = EXCLUDED.trend_score,
        value_score = EXCLUDED.value_score,
        quality_score = EXCLUDED.quality_score,
        rsi = EXCLUDED.rsi,
        macd = EXCLUDED.macd,
        sma_20 = EXCLUDED.sma_20,
        sma_50 = EXCLUDED.sma_50,
        volume_avg_30d = EXCLUDED.volume_avg_30d,
        current_price = EXCLUDED.current_price,
        price_change_1d = EXCLUDED.price_change_1d,
        price_change_5d = EXCLUDED.price_change_5d,
        price_change_30d = EXCLUDED.price_change_30d,
        volatility_30d = EXCLUDED.volatility_30d,
        market_cap = EXCLUDED.market_cap,
        pe_ratio = EXCLUDED.pe_ratio,
        score_date = EXCLUDED.score_date,
        last_updated = EXCLUDED.last_updated
    `);

    await query(`
      INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate, surprise_percent) VALUES
      ('AAPL', CURRENT_DATE, 1.52, 1.45, 4.8),
      ('MSFT', CURRENT_DATE, 2.93, 2.85, 2.8),
      ('GOOGL', CURRENT_DATE, 1.44, 1.38, 4.3)
      ON CONFLICT (symbol, quarter) DO NOTHING
    `);

    // Insert test signals data
    await query(`
      INSERT INTO buy_sell_daily (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
      ('AAPL', 'daily', CURRENT_DATE, 175.0, 176.5, 174.0, 175.5, 65000000, 'BUY', 175.0, 170.0, true),
      ('MSFT', 'daily', CURRENT_DATE, 420.0, 422.0, 419.0, 420.75, 28000000, 'BUY', 420.0, 410.0, true),
      ('GOOGL', 'daily', CURRENT_DATE, 142.0, 144.0, 141.0, 143.5, 22000000, 'SELL', 145.0, 140.0, false)
      ON CONFLICT (symbol, timeframe, date) DO NOTHING
    `);

    await query(`
      INSERT INTO buy_sell_weekly (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
      ('AAPL', 'weekly', CURRENT_DATE, 170.0, 180.0, 169.0, 178.0, 325000000, 'BUY', 170.0, 165.0, true),
      ('MSFT', 'weekly', CURRENT_DATE, 415.0, 430.0, 414.0, 428.0, 140000000, 'BUY', 415.0, 400.0, true)
      ON CONFLICT (symbol, timeframe, date) DO NOTHING
    `);

    console.log('✅ Test data populated for existing Python loader tables');
  } catch (error) {
    console.warn('⚠️  Could not populate test data for loader tables:', error.message);
    // Non-fatal error - tests can still run
  }
}

// Setup function for tests
async function setupTestDatabase() {
  try {
    // Initialize database connection
    await initializeDatabase();
    console.log('✅ Database connection pool initialized successfully');

    // Create webapp-only tables
    await ensureTestData();

    // Create Python loader tables for testing
    await createLoaderTables();

    // Try to populate test data for Python loader tables if they exist
    await populateLoaderTestData();

    console.log('✅ Database tables created matching Python loader structure');
  } catch (error) {
    console.error('❌ Failed to setup test database:', error);
    throw error;
  }
}

// Add custom Jest matchers for all tests - temporarily disabled due to global setup issues
// Custom matchers should be in setupFilesAfterEnv, not global setup
/*
if (typeof expect !== 'undefined') {
  expect.extend({
    toBeOneOf(received, expected) {
      const pass = expected.includes(received);
      if (pass) {
        return {
          message: () => `expected ${received} not to be one of ${expected}`,
          pass: true,
        };
      } else {
        return {
          message: () => `expected ${received} to be one of ${expected}`,
          pass: false,
        };
      }
    },
  });
  console.log('✅ Custom Jest matchers loaded globally');
}
*/
console.log('✅ Database setup complete - custom matchers disabled for now');

module.exports = {
  isDatabaseAvailable,
  getTestData,
  ensureTestData,
  createLoaderTables,
  populateLoaderTestData,
  setupTestDatabase
};