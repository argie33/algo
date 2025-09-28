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
      const transactionCount = await query('SELECT COUNT(*) FROM portfolio_transactions');
      if (parseInt(transactionCount.rows[0].count) === 0) {
        console.log('📝 Inserting test transaction data (LOCAL ONLY)...');

        // Create transaction data for all authentication user IDs
        const testUsers = ['default_user', 'dev-user-bypass', 'test-user-123', 'mock-user-123'];

        for (const userId of testUsers) {
          const insertTransactions = `
            INSERT INTO portfolio_transactions (symbol, transaction_type, quantity, price, total_amount, commission, transaction_date, settlement_date, notes, user_id, broker) VALUES
            ('AAPL', 'BUY', 100.00, 150.00, 15000.00, 7.50, '2024-01-01', '2024-01-03', 'Initial AAPL purchase', $1, 'manual'),
            ('MSFT', 'BUY', 50.00, 400.00, 20000.00, 5.00, '2024-01-02', '2024-01-04', 'MSFT position', $1, 'manual'),
            ('GOOGL', 'BUY', 50.00, 160.00, 8000.00, 4.00, '2024-01-03', '2024-01-05', 'GOOGL initial purchase', $1, 'manual'),
            ('GOOGL', 'SELL', 25.00, 140.00, 3500.00, 3.50, '2024-01-05', '2024-01-07', 'Partial GOOGL sale', $1, 'manual'),
            ('TSLA', 'BUY', 30.00, 250.00, 7500.00, 4.00, '2024-01-10', '2024-01-12', 'Tesla investment', $1, 'manual'),
            ('AMZN', 'DIVIDEND', 10.00, 3.50, 35.00, 0.00, '2024-01-15', '2024-01-15', 'Quarterly dividend', $1, 'manual')
          `;
          await query(insertTransactions, [userId]);
          console.log(`✅ Test transaction data inserted for ${userId} (LOCAL ONLY)`);
        }
      } else {
        console.log('📊 Transaction data already exists');
      }
    } else {
      console.log('🏭 Production/Staging environment - skipping test data insertion');
    }

    // Clear existing holdings for all test users
    const testUsers = ['default_user', 'dev-user-bypass', 'test-user-123', 'mock-user-123'];
    for (const userId of testUsers) {
      await query('DELETE FROM portfolio_holdings WHERE user_id = $1', [userId]);
    }
    console.log('🗑️ Cleared existing holdings for all test users');

    // Calculate and insert portfolio holdings from transactions for all test users
    for (const userId of testUsers) {
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
          CASE symbol
            WHEN 'AAPL' THEN 175.50
            WHEN 'MSFT' THEN 420.75
            WHEN 'GOOGL' THEN 143.50
            WHEN 'TSLA' THEN 285.00
            WHEN 'AMZN' THEN 148.90
            ELSE 100.00
          END as current_price,
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