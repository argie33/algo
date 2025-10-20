// Portfolio Data Sync Script
// Syncs portfolio_transactions to portfolio_holdings for local PostgreSQL testing

const { query, initializeDatabase } = require('./utils/database');

async function syncPortfolioData() {
  try {
    console.log('🔄 Starting portfolio data sync...');

    // Initialize database connection
    await initializeDatabase();
    console.log('✅ Database connection established');

    // Check if tables exist
    const checkTablesQuery = `
      SELECT table_name
      FROM information_schema.tables
      WHERE table_name IN ('portfolio_transactions', 'portfolio_holdings')
    `;
    const tableCheck = await query(checkTablesQuery);
    console.log('📋 Existing tables:', tableCheck.rows.map(r => r.table_name));

    // Create portfolio_transactions table if it doesn't exist
    const createTransactionsTable = `
      CREATE TABLE IF NOT EXISTS portfolio_transactions (
        transaction_id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        transaction_type VARCHAR(20) NOT NULL,
        quantity DECIMAL(15,4) NOT NULL,
        price DECIMAL(15,4) NOT NULL,
        total_amount DECIMAL(15,4) NOT NULL,
        commission DECIMAL(10,4) DEFAULT 0.00,
        transaction_date TIMESTAMP NOT NULL,
        settlement_date TIMESTAMP,
        notes TEXT,
        user_id VARCHAR(50) NOT NULL,
        broker VARCHAR(50) DEFAULT 'manual',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `;
    await query(createTransactionsTable);
    console.log('✅ portfolio_transactions table ensured');

    // Check existing portfolio_holdings schema and add missing columns if needed
    try {
      // Add missing columns to existing table
      await query('ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS unrealized_pnl DECIMAL(15,4) DEFAULT 0');
      await query('ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS unrealized_pnl_percent DECIMAL(10,4) DEFAULT 0');
      await query('ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP');
      console.log('✅ portfolio_holdings schema updated with missing columns');
    } catch (error) {
      console.warn('Warning updating portfolio_holdings schema:', error.message);

      // Fallback: create table if it doesn't exist
      const createHoldingsTable = `
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          symbol VARCHAR(10) NOT NULL,
          quantity DECIMAL(15,8) NOT NULL,
          average_cost DECIMAL(10,4) NOT NULL,
          current_price DECIMAL(10,4),
          market_value DECIMAL(15,2),
          unrealized_pnl DECIMAL(15,4) DEFAULT 0,
          unrealized_pnl_percent DECIMAL(10,4) DEFAULT 0,
          last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, symbol)
        )
      `;
      await query(createHoldingsTable);
      console.log('✅ portfolio_holdings table created');
    }

    // LOCAL ONLY: Insert test transaction data if table is empty and environment is local
    const environment = process.env.ENVIRONMENT || process.env.NODE_ENV || 'local';
    const isLocal = environment === 'local' || environment === 'test' || environment === 'development';

    if (isLocal) {
      // NOTE: Test data should only be inserted via proper test migrations/fixtures
      // NOT via inline scripts that run during production sync
      console.log('📝 Database initialization handled by migration scripts');
    } else {
      console.log('🏭 Production environment - database sync active');
    }

    // Calculate and insert portfolio holdings from transactions for all users with transactions
    // Get distinct user IDs from actual transactions in database
    const getUsersQuery = `SELECT DISTINCT user_id FROM portfolio_transactions ORDER BY user_id`;
    const usersResult = await query(getUsersQuery);
    const dbUsers = usersResult.rows.map(row => row.user_id);

    if (dbUsers.length === 0) {
      console.log('⚠️  No users found in portfolio_transactions');
    } else {
      console.log(`Processing holdings for ${dbUsers.length} users with transactions`);
    }

    for (const userId of dbUsers) {
      const calculateHoldings = `
        INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value, unrealized_pnl, unrealized_pnl_percent, last_updated)
        SELECT
          user_id,
          symbol,
          SUM(CASE
            WHEN transaction_type = 'BUY' THEN quantity
            WHEN transaction_type = 'SELL' THEN -quantity
            ELSE 0
          END) as total_quantity,
          CASE
            WHEN SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE 0 END) > 0 THEN
              SUM(CASE WHEN transaction_type = 'BUY' THEN total_amount ELSE 0 END) /
              SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE 0 END)
            ELSE 0
          END as avg_cost,
          NULL as current_price,
          0 as market_value,
          0 as unrealized_pnl,
          0 as unrealized_pnl_percent,
          CURRENT_TIMESTAMP as last_updated
        FROM portfolio_transactions
        WHERE user_id = $1 AND transaction_type IN ('BUY', 'SELL')
        GROUP BY user_id, symbol
        HAVING SUM(CASE
          WHEN transaction_type = 'BUY' THEN quantity
          WHEN transaction_type = 'SELL' THEN -quantity
          ELSE 0
        END) > 0
      `;
      await query(calculateHoldings, [userId]);
      console.log(`✅ Portfolio holdings calculated for ${userId}`);
    }

    // Update market values and PnL
    const updateValues = `
      UPDATE portfolio_holdings SET
        market_value = quantity * current_price,
        unrealized_pnl = (current_price - average_cost) * quantity,
        unrealized_pnl_percent = CASE
          WHEN average_cost > 0 THEN ((current_price - average_cost) / average_cost) * 100
          ELSE 0
        END,
        last_updated = CURRENT_TIMESTAMP
      WHERE user_id = 'default_user'
    `;
    await query(updateValues);
    console.log('✅ Market values and PnL updated');

    // Show final results
    const holdings = await query('SELECT * FROM portfolio_holdings WHERE user_id = $1', ['default_user']);
    console.log('📈 Final holdings:', holdings.rows);

    console.log('🎉 Portfolio data sync completed successfully!');
    process.exit(0);

  } catch (error) {
    console.error('❌ Portfolio sync error:', error);
    process.exit(1);
  }
}

// Run the sync
syncPortfolioData();