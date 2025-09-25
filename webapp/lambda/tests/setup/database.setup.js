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
      const setupSqlPath = path.join(__dirname, '../../setup_database.sql');
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

  } catch (error) {
    console.error('❌ Error creating webapp tables:', error);
    throw error;
  }
}

// Function to create Python loader tables for testing
async function createLoaderTables() {
  try {
    // Create company_profile table from loadinfo.py
    await query(`
      CREATE TABLE IF NOT EXISTS company_profile (
        ticker VARCHAR(10) PRIMARY KEY,
        short_name VARCHAR(100),
        long_name VARCHAR(200),
        sector VARCHAR(100),
        industry VARCHAR(100)
      )
    `);

    // Create market_data table from loadinfo.py
    await query(`
      CREATE TABLE IF NOT EXISTS market_data (
        ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
        current_price NUMERIC,
        market_cap BIGINT,
        volume BIGINT
      )
    `);

    // Create key_metrics table from loadinfo.py
    await query(`
      CREATE TABLE IF NOT EXISTS key_metrics (
        ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
        trailing_pe NUMERIC,
        forward_pe NUMERIC,
        dividend_yield NUMERIC,
        eps_trailing NUMERIC
      )
    `);

    // Create price_daily table from loadpricedaily.py
    await query(`
      CREATE TABLE IF NOT EXISTS price_daily (
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        adj_close DOUBLE PRECISION,
        volume BIGINT,
        PRIMARY KEY (symbol, date)
      )
    `);

    // Create earnings_history table from loadearningshistory.py
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

    console.log('✅ Python loader tables created for testing');
  } catch (error) {
    console.error('❌ Error creating Python loader tables:', error);
    throw error;
  }
}

// Function to populate test data for Python loader tables (will only work if tables exist)
async function populateLoaderTestData() {
  try {
    // Insert test data into Python loader tables
    await query(`
      INSERT INTO company_profile (ticker, short_name, long_name, sector, industry) VALUES
      ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics'),
      ('MSFT', 'Microsoft Corp.', 'Microsoft Corporation', 'Technology', 'Software'),
      ('GOOGL', 'Alphabet Inc.', 'Alphabet Inc.', 'Technology', 'Internet Services')
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      INSERT INTO market_data (ticker, current_price, market_cap, volume) VALUES
      ('AAPL', 175.50, 3400000000000, 65000000),
      ('MSFT', 420.75, 3200000000000, 28000000),
      ('GOOGL', 143.50, 1800000000000, 22000000)
      ON CONFLICT (ticker) DO NOTHING
    `);

    await query(`
      INSERT INTO key_metrics (ticker, trailing_pe, forward_pe, dividend_yield, eps_trailing) VALUES
      ('AAPL', 28.5, 25.2, 0.55, 6.15),
      ('MSFT', 35.8, 29.1, 0.80, 11.75),
      ('GOOGL', 24.2, 21.5, 0.00, 5.89)
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
      INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate, surprise_percent) VALUES
      ('AAPL', CURRENT_DATE, 1.52, 1.45, 4.8),
      ('MSFT', CURRENT_DATE, 2.93, 2.85, 2.8),
      ('GOOGL', CURRENT_DATE, 1.44, 1.38, 4.3)
      ON CONFLICT (symbol, quarter) DO NOTHING
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

module.exports = {
  isDatabaseAvailable,
  getTestData,
  ensureTestData,
  createLoaderTables,
  populateLoaderTestData,
  setupTestDatabase
};