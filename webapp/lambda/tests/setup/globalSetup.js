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
      INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price) VALUES
      ('test-user-123', 'AAPL', 10.0, 150.00, 175.50),
      ('test-user-123', 'MSFT', 5.0, 300.00, 420.75)
      ON CONFLICT (user_id, symbol) DO NOTHING
    `);

      console.log('✅ Global Setup: Webapp-only tables created successfully (fallback)');
    }

  } catch (error) {
    console.error('❌ Global setup failed:', error);
    // Don't throw - allow tests to continue and fail gracefully if needed
  }
};