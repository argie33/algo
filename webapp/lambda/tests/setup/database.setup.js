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
        volume_ratio DECIMAL(8,6),
        beta DECIMAL(8,6),
        asset_class VARCHAR(50),
        region VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
      )
    `);

    // fundamental_metrics table removed - using actual loader tables instead

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
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Add unique constraint separately to handle existing tables
    try {
      await query(`
        ALTER TABLE price_daily
        ADD CONSTRAINT unique_symbol_date
        UNIQUE (symbol, date)
      `);
    } catch (error) {
      // Ignore error if constraint already exists
      if (!error.message.includes('already exists') && !error.message.includes('relation "unique_symbol_date" already exists')) {
        console.warn('Could not add unique constraint to price_daily:', error.message);
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

    await query(`
      INSERT INTO market_data (ticker, market_cap, current_price, volume) VALUES
      ('AAPL', 3500000000000, 150.25, 65000000),
      ('MSFT', 2800000000000, 350.75, 45000000),
      ('SPY', 400000000000, 446.95, 65000000),
      ('QQQ', 200000000000, 387.30, 42000000)
      ON CONFLICT (ticker) DO NOTHING
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