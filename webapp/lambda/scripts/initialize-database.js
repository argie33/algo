/**
 * Database Schema Initialization Script
 * 
 * This script creates all required tables for the financial webapp.
 * Can be run from Lambda environment or locally for development.
 */

const { query, transaction } = require('../utils/database');

const REQUIRED_TABLES = {
  // User management
  'users': `
    CREATE TABLE IF NOT EXISTS users (
      id VARCHAR(255) PRIMARY KEY,
      username VARCHAR(100) UNIQUE NOT NULL,
      email VARCHAR(255) UNIQUE NOT NULL,
      first_name VARCHAR(100),
      last_name VARCHAR(100),
      phone VARCHAR(20),
      timezone VARCHAR(50) DEFAULT 'America/New_York',
      currency VARCHAR(3) DEFAULT 'USD',
      two_factor_enabled BOOLEAN DEFAULT FALSE,
      two_factor_secret VARCHAR(255),
      recovery_codes TEXT,
      deleted_at TIMESTAMP,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `,
  
  // Stock data
  'stocks': `
    CREATE TABLE IF NOT EXISTS stocks (
      ticker VARCHAR(10) PRIMARY KEY,
      company_name VARCHAR(255) NOT NULL,
      short_name VARCHAR(100),
      exchange VARCHAR(10),
      sector VARCHAR(100),
      industry VARCHAR(255),
      market_cap BIGINT,
      shares_outstanding BIGINT,
      price DECIMAL(10,2),
      volume BIGINT,
      avg_volume BIGINT,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `,
  
  // Market data
  'market_data': `
    CREATE TABLE IF NOT EXISTS market_data (
      symbol VARCHAR(10) PRIMARY KEY,
      current_price DECIMAL(10,2),
      price_change DECIMAL(10,2),
      price_change_percent DECIMAL(5,2),
      day_high DECIMAL(10,2),
      day_low DECIMAL(10,2),
      volume BIGINT,
      avg_volume BIGINT,
      market_cap BIGINT,
      pe_ratio DECIMAL(8,2),
      dividend_yield DECIMAL(5,2),
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `,
  
  // Financial statements
  'annual_balance_sheet': `
    CREATE TABLE IF NOT EXISTS annual_balance_sheet (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  'quarterly_balance_sheet': `
    CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  'annual_income_statement': `
    CREATE TABLE IF NOT EXISTS annual_income_statement (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  'quarterly_income_statement': `
    CREATE TABLE IF NOT EXISTS quarterly_income_statement (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  'ttm_income_stmt': `
    CREATE TABLE IF NOT EXISTS ttm_income_stmt (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  'annual_cash_flow': `
    CREATE TABLE IF NOT EXISTS annual_cash_flow (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  'quarterly_cash_flow': `
    CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  'ttm_cashflow': `
    CREATE TABLE IF NOT EXISTS ttm_cashflow (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      item_name VARCHAR(255) NOT NULL,
      value DECIMAL(20,2),
      fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, date, item_name)
    )
  `,
  
  // Key metrics
  'key_metrics': `
    CREATE TABLE IF NOT EXISTS key_metrics (
      ticker VARCHAR(10) PRIMARY KEY,
      trailing_pe DECIMAL(8,2),
      forward_pe DECIMAL(8,2),
      price_to_sales_ttm DECIMAL(8,2),
      price_to_book DECIMAL(8,2),
      book_value DECIMAL(10,2),
      peg_ratio DECIMAL(8,2),
      enterprise_value BIGINT,
      ev_to_revenue DECIMAL(8,2),
      ev_to_ebitda DECIMAL(8,2),
      total_revenue BIGINT,
      net_income BIGINT,
      ebitda BIGINT,
      gross_profit BIGINT,
      eps_trailing DECIMAL(8,2),
      eps_forward DECIMAL(8,2),
      eps_current_year DECIMAL(8,2),
      price_eps_current_year DECIMAL(8,2),
      earnings_q_growth_pct DECIMAL(5,2),
      revenue_growth_pct DECIMAL(5,2),
      earnings_growth_pct DECIMAL(5,2),
      total_cash BIGINT,
      cash_per_share DECIMAL(8,2),
      operating_cashflow BIGINT,
      free_cashflow BIGINT,
      total_debt BIGINT,
      debt_to_equity DECIMAL(8,2),
      quick_ratio DECIMAL(8,2),
      current_ratio DECIMAL(8,2),
      profit_margin_pct DECIMAL(5,2),
      gross_margin_pct DECIMAL(5,2),
      ebitda_margin_pct DECIMAL(5,2),
      operating_margin_pct DECIMAL(5,2),
      return_on_assets_pct DECIMAL(5,2),
      return_on_equity_pct DECIMAL(5,2),
      dividend_rate DECIMAL(8,2),
      dividend_yield DECIMAL(5,2),
      five_year_avg_dividend_yield DECIMAL(5,2),
      payout_ratio DECIMAL(5,2),
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `,
  
  // Portfolio management
  'portfolios': `
    CREATE TABLE IF NOT EXISTS portfolios (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      is_default BOOLEAN DEFAULT FALSE,
      total_value DECIMAL(15,2) DEFAULT 0,
      total_cost DECIMAL(15,2) DEFAULT 0,
      total_gain_loss DECIMAL(15,2) DEFAULT 0,
      total_gain_loss_percent DECIMAL(5,2) DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `,
  
  'portfolio_holdings': `
    CREATE TABLE IF NOT EXISTS portfolio_holdings (
      id SERIAL PRIMARY KEY,
      portfolio_id INTEGER NOT NULL,
      symbol VARCHAR(10) NOT NULL,
      shares DECIMAL(12,4) NOT NULL,
      average_cost DECIMAL(10,2) NOT NULL,
      current_price DECIMAL(10,2),
      total_value DECIMAL(15,2),
      gain_loss DECIMAL(15,2),
      gain_loss_percent DECIMAL(5,2),
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(portfolio_id, symbol)
    )
  `,
  
  // User preferences
  'user_notification_preferences': `
    CREATE TABLE IF NOT EXISTS user_notification_preferences (
      user_id VARCHAR(255) PRIMARY KEY,
      email_notifications BOOLEAN DEFAULT TRUE,
      push_notifications BOOLEAN DEFAULT TRUE,
      price_alerts BOOLEAN DEFAULT TRUE,
      portfolio_updates BOOLEAN DEFAULT TRUE,
      market_news BOOLEAN DEFAULT FALSE,
      weekly_reports BOOLEAN DEFAULT TRUE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `,
  
  'user_theme_preferences': `
    CREATE TABLE IF NOT EXISTS user_theme_preferences (
      user_id VARCHAR(255) PRIMARY KEY,
      dark_mode BOOLEAN DEFAULT FALSE,
      primary_color VARCHAR(20) DEFAULT '#1976d2',
      chart_style VARCHAR(20) DEFAULT 'candlestick',
      layout VARCHAR(20) DEFAULT 'standard',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `,
  
  // API keys (legacy compatibility)
  'user_api_keys': `
    CREATE TABLE IF NOT EXISTS user_api_keys (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      provider VARCHAR(50) NOT NULL,
      api_key_encrypted TEXT NOT NULL,
      api_secret_encrypted TEXT,
      description VARCHAR(255),
      is_sandbox BOOLEAN DEFAULT TRUE,
      is_active BOOLEAN DEFAULT TRUE,
      last_used TIMESTAMP,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id, provider)
    )
  `
};

const SAMPLE_DATA = {
  stocks: `
    INSERT INTO stocks (ticker, company_name, short_name, exchange, sector, industry) VALUES
      ('AAPL', 'Apple Inc.', 'Apple', 'NASDAQ', 'Technology', 'Consumer Electronics'),
      ('GOOGL', 'Alphabet Inc.', 'Google', 'NASDAQ', 'Technology', 'Internet Software'),
      ('MSFT', 'Microsoft Corporation', 'Microsoft', 'NASDAQ', 'Technology', 'Software'),
      ('AMZN', 'Amazon.com Inc.', 'Amazon', 'NASDAQ', 'Consumer Discretionary', 'E-commerce'),
      ('TSLA', 'Tesla, Inc.', 'Tesla', 'NASDAQ', 'Consumer Discretionary', 'Electric Vehicles'),
      ('NVDA', 'NVIDIA Corporation', 'NVIDIA', 'NASDAQ', 'Technology', 'Semiconductors'),
      ('META', 'Meta Platforms, Inc.', 'Meta', 'NASDAQ', 'Technology', 'Social Media'),
      ('JPM', 'JPMorgan Chase & Co.', 'JPMorgan', 'NYSE', 'Finance', 'Banking'),
      ('JNJ', 'Johnson & Johnson', 'J&J', 'NYSE', 'Healthcare', 'Pharmaceuticals'),
      ('V', 'Visa Inc.', 'Visa', 'NYSE', 'Finance', 'Payment Processing')
    ON CONFLICT (ticker) DO NOTHING
  `,
  
  market_data: `
    INSERT INTO market_data (symbol, current_price, price_change, price_change_percent, volume) VALUES
      ('AAPL', 150.25, 2.15, 1.45, 50000000),
      ('GOOGL', 2800.50, -15.25, -0.54, 1200000),
      ('MSFT', 300.75, 5.20, 1.76, 25000000),
      ('AMZN', 3200.00, -8.75, -0.27, 3500000),
      ('TSLA', 850.30, 12.50, 1.49, 28000000)
    ON CONFLICT (symbol) DO NOTHING
  `
};

const INDEXES = [
  'CREATE INDEX IF NOT EXISTS idx_stocks_ticker ON stocks(ticker)',
  'CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol)',
  'CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol_date ON annual_balance_sheet(symbol, date DESC)',
  'CREATE INDEX IF NOT EXISTS idx_annual_income_statement_symbol_date ON annual_income_statement(symbol, date DESC)',
  'CREATE INDEX IF NOT EXISTS idx_annual_cash_flow_symbol_date ON annual_cash_flow(symbol, date DESC)',
  'CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_portfolio_id ON portfolio_holdings(portfolio_id)',
  'CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)',
  'CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)'
];

async function initializeDatabase(options = {}) {
  const { 
    createTables = true, 
    createIndexes = true, 
    insertSampleData = true,
    verbose = true 
  } = options;
  
  console.log('🚀 Starting database schema initialization...');
  
  try {
    const results = await transaction(async (client) => {
      const creationResults = [];
      
      // Create tables
      if (createTables) {
        console.log('📋 Creating database tables...');
        
        for (const [tableName, sql] of Object.entries(REQUIRED_TABLES)) {
          try {
            await client.query(sql);
            creationResults.push(`✅ Table created: ${tableName}`);
            if (verbose) console.log(`✅ Created table: ${tableName}`);
          } catch (error) {
            const errorMsg = `❌ Failed to create table ${tableName}: ${error.message}`;
            creationResults.push(errorMsg);
            if (verbose) console.error(errorMsg);
          }
        }
      }
      
      // Create indexes
      if (createIndexes) {
        console.log('🔗 Creating database indexes...');
        
        for (const indexSql of INDEXES) {
          try {
            await client.query(indexSql);
            const indexName = indexSql.match(/idx_[\w_]+/)?.[0] || 'index';
            creationResults.push(`✅ Index created: ${indexName}`);
            if (verbose) console.log(`✅ Created index: ${indexName}`);
          } catch (error) {
            const errorMsg = `❌ Failed to create index: ${error.message}`;
            creationResults.push(errorMsg);
            if (verbose) console.error(errorMsg);
          }
        }
      }
      
      // Insert sample data
      if (insertSampleData) {
        console.log('📊 Inserting sample data...');
        
        for (const [tableName, sql] of Object.entries(SAMPLE_DATA)) {
          try {
            const result = await client.query(sql);
            creationResults.push(`✅ Sample data inserted: ${tableName} (${result.rowCount} rows)`);
            if (verbose) console.log(`✅ Inserted sample data: ${tableName}`);
          } catch (error) {
            const errorMsg = `❌ Failed to insert sample data for ${tableName}: ${error.message}`;
            creationResults.push(errorMsg);
            if (verbose) console.error(errorMsg);
          }
        }
      }
      
      return creationResults;
    });
    
    console.log('✅ Database initialization completed successfully!');
    
    return {
      success: true,
      message: 'Database schema initialization completed',
      results,
      tablesCreated: Object.keys(REQUIRED_TABLES).length,
      indexesCreated: INDEXES.length,
      timestamp: new Date().toISOString()
    };
    
  } catch (error) {
    console.error('❌ Database initialization failed:', error);
    
    return {
      success: false,
      error: error.message,
      message: 'Database schema initialization failed',
      timestamp: new Date().toISOString()
    };
  }
}

// Validate existing schema
async function validateDatabaseSchema() {
  console.log('🔍 Validating database schema...');
  
  try {
    const missingTables = [];
    const existingTables = [];
    
    for (const tableName of Object.keys(REQUIRED_TABLES)) {
      try {
        const result = await query(`
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = $1
          )
        `, [tableName]);
        
        if (result.rows[0].exists) {
          existingTables.push(tableName);
        } else {
          missingTables.push(tableName);
        }
      } catch (error) {
        missingTables.push(tableName);
      }
    }
    
    return {
      success: true,
      totalTables: Object.keys(REQUIRED_TABLES).length,
      existingTables: existingTables.length,
      missingTables: missingTables.length,
      missingTableNames: missingTables,
      existingTableNames: existingTables,
      needsInitialization: missingTables.length > 0
    };
    
  } catch (error) {
    return {
      success: false,
      error: error.message,
      needsInitialization: true
    };
  }
}

// Export functions for use in other modules
module.exports = {
  initializeDatabase,
  validateDatabaseSchema,
  REQUIRED_TABLES,
  SAMPLE_DATA,
  INDEXES
};

// Allow direct execution
if (require.main === module) {
  initializeDatabase()
    .then(result => {
      console.log('📊 Initialization Result:', result);
      process.exit(result.success ? 0 : 1);
    })
    .catch(error => {
      console.error('💥 Fatal error:', error);
      process.exit(1);
    });
}