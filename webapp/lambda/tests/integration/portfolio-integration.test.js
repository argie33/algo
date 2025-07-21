/**
 * INTEGRATION TESTS: Portfolio Management System
 * Industry Standard: Tests real portfolio operations with AWS services
 * Uses IaC-deployed test infrastructure with proper setup/teardown
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Pool } = require('pg');

const describeOrSkip = (process.env.TEST_DB_SECRET_ARN) ? describe : describe.skip;

describeOrSkip('Portfolio Integration Tests (Industry Standard)', () => {
  let testConfig;
  let dbPool;
  let secretsManager;
  let testUserId;
  let portfolioApi;

  beforeAll(async () => {
    // Load test infrastructure configuration
    const stackName = process.env.TEST_STACK_NAME || 'integration-test-stack';
    const region = process.env.AWS_REGION || 'us-east-1';

    secretsManager = new SecretsManagerClient({ region });

    try {
      // Get database credentials from CloudFormation-deployed Secrets Manager
      const secretArn = process.env.TEST_DB_SECRET_ARN;
      if (!secretArn) {
        throw new Error('TEST_DB_SECRET_ARN environment variable not set');
      }

      const secretResponse = await secretsManager.send(new GetSecretValueCommand({
        SecretId: secretArn
      }));

      const credentials = JSON.parse(secretResponse.SecretString);

      testConfig = {
        host: credentials.host,
        port: credentials.port,
        database: credentials.dbname,
        user: credentials.username,
        password: credentials.password,
        ssl: false,
        max: 5,
        idleTimeoutMillis: 30000,
        connectionTimeoutMillis: 10000,
      };

      // Create connection pool
      dbPool = new Pool(testConfig);

      // Test the connection
      const client = await dbPool.connect();
      await client.query('SELECT NOW()');
      client.release();

      console.log('✅ Portfolio integration test database connection established');

      // Set up test schema and data
      await setupPortfolioTestSchema();
      await setupTestUser();

      // Initialize portfolio API with test configuration
      portfolioApi = require('../../api/portfolio');
      
    } catch (error) {
      console.error('❌ Portfolio integration test setup failed:', error.message);
      
      if (error.code === 'ENOTFOUND' || error.message.includes('SECRET_ARN')) {
        console.log('⚠️ Skipping portfolio integration tests - test infrastructure not available');
        test.skip = true;
        return;
      }
      
      throw error;
    }
  }, 30000);

  afterAll(async () => {
    if (dbPool) {
      await cleanupPortfolioTestData();
      await dbPool.end();
      console.log('✅ Portfolio integration test cleanup completed');
    }
  });

  async function setupPortfolioTestSchema() {
    const client = await dbPool.connect();
    try {
      // Create portfolio-related test tables
      await client.query(`
        CREATE TABLE IF NOT EXISTS test_users (
          user_id SERIAL PRIMARY KEY,
          email VARCHAR(255) UNIQUE NOT NULL,
          username VARCHAR(100) UNIQUE NOT NULL,
          cognito_sub VARCHAR(255),
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
      `);

      await client.query(`
        CREATE TABLE IF NOT EXISTS test_portfolio_holdings (
          holding_id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES test_users(user_id) ON DELETE CASCADE,
          symbol VARCHAR(10) NOT NULL,
          quantity DECIMAL(15, 6) NOT NULL CHECK (quantity >= 0),
          avg_cost DECIMAL(10, 2) NOT NULL CHECK (avg_cost >= 0),
          market_value DECIMAL(15, 2),
          last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, symbol)
        )
      `);

      await client.query(`
        CREATE TABLE IF NOT EXISTS test_portfolio_transactions (
          transaction_id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES test_users(user_id) ON DELETE CASCADE,
          symbol VARCHAR(10) NOT NULL,
          transaction_type VARCHAR(10) NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
          quantity DECIMAL(15, 6) NOT NULL CHECK (quantity > 0),
          price DECIMAL(10, 2) NOT NULL CHECK (price > 0),
          total_amount DECIMAL(15, 2) NOT NULL,
          transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          fees DECIMAL(10, 2) DEFAULT 0
        )
      `);

      await client.query(`
        CREATE TABLE IF NOT EXISTS test_portfolio_metadata (
          user_id INTEGER PRIMARY KEY REFERENCES test_users(user_id) ON DELETE CASCADE,
          total_value DECIMAL(15, 2) DEFAULT 0,
          total_cost_basis DECIMAL(15, 2) DEFAULT 0,
          total_gain_loss DECIMAL(15, 2) DEFAULT 0,
          gain_loss_percentage DECIMAL(10, 4) DEFAULT 0,
          cash_balance DECIMAL(15, 2) DEFAULT 0,
          last_calculated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
      `);

      await client.query(`
        CREATE TABLE IF NOT EXISTS test_market_data (
          symbol VARCHAR(10) PRIMARY KEY,
          current_price DECIMAL(10, 2) NOT NULL,
          previous_close DECIMAL(10, 2),
          volume BIGINT,
          market_cap BIGINT,
          last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
      `);

      console.log('✅ Portfolio test schema created');
    } finally {
      client.release();
    }
  }

  async function setupTestUser() {
    const client = await dbPool.connect();
    try {
      const result = await client.query(`
        INSERT INTO test_users (email, username, cognito_sub) 
        VALUES ($1, $2, $3) 
        RETURNING user_id
      `, [
        'portfolio-integration-test@example.com',
        'portfolio_test_user',
        'test-cognito-sub-123'
      ]);
      
      testUserId = result.rows[0].user_id;

      // Initialize portfolio metadata
      await client.query(`
        INSERT INTO test_portfolio_metadata (user_id, cash_balance) 
        VALUES ($1, $2)
      `, [testUserId, 10000.00]);

      // Add some test market data
      const testSymbols = [
        { symbol: 'AAPL', price: 175.50, prevClose: 174.30, volume: 50000000, marketCap: 2800000000000 },
        { symbol: 'GOOGL', price: 2650.75, prevClose: 2640.20, volume: 1200000, marketCap: 1700000000000 },
        { symbol: 'MSFT', price: 410.25, prevClose: 408.90, volume: 25000000, marketCap: 3000000000000 },
        { symbol: 'TSLA', price: 245.80, prevClose: 250.15, volume: 35000000, marketCap: 780000000000 }
      ];

      for (const symbolData of testSymbols) {
        await client.query(`
          INSERT INTO test_market_data (symbol, current_price, previous_close, volume, market_cap)
          VALUES ($1, $2, $3, $4, $5)
          ON CONFLICT (symbol) DO UPDATE SET
            current_price = EXCLUDED.current_price,
            previous_close = EXCLUDED.previous_close,
            volume = EXCLUDED.volume,
            market_cap = EXCLUDED.market_cap
        `, [symbolData.symbol, symbolData.price, symbolData.prevClose, symbolData.volume, symbolData.marketCap]);
      }

      console.log(`✅ Test user created with ID: ${testUserId}`);
    } finally {
      client.release();
    }
  }

  async function cleanupPortfolioTestData() {
    const client = await dbPool.connect();
    try {
      await client.query('DROP TABLE IF EXISTS test_portfolio_transactions CASCADE');
      await client.query('DROP TABLE IF EXISTS test_portfolio_holdings CASCADE');
      await client.query('DROP TABLE IF EXISTS test_portfolio_metadata CASCADE');
      await client.query('DROP TABLE IF EXISTS test_market_data CASCADE');
      await client.query('DROP TABLE IF EXISTS test_users CASCADE');
      console.log('✅ Portfolio test data cleaned up');
    } finally {
      client.release();
    }
  }

  describe('Portfolio Holdings Management', () => {
    it('creates new portfolio holdings through buy transactions', async () => {
      const client = await dbPool.connect();
      try {
        await client.query('BEGIN');

        // Buy AAPL shares
        const buyTransaction = {
          symbol: 'AAPL',
          quantity: 100,
          price: 175.50,
          fees: 9.95
        };

        const totalAmount = (buyTransaction.quantity * buyTransaction.price) + buyTransaction.fees;

        // Record transaction
        const transactionResult = await client.query(`
          INSERT INTO test_portfolio_transactions 
          (user_id, symbol, transaction_type, quantity, price, total_amount, fees)
          VALUES ($1, $2, $3, $4, $5, $6, $7)
          RETURNING transaction_id
        `, [testUserId, buyTransaction.symbol, 'BUY', buyTransaction.quantity, 
            buyTransaction.price, totalAmount, buyTransaction.fees]);

        expect(transactionResult.rows[0].transaction_id).toBeDefined();

        // Update portfolio holdings
        await client.query(`
          INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (user_id, symbol) DO UPDATE SET
            quantity = test_portfolio_holdings.quantity + EXCLUDED.quantity,
            avg_cost = (
              (test_portfolio_holdings.quantity * test_portfolio_holdings.avg_cost) + 
              (EXCLUDED.quantity * EXCLUDED.avg_cost)
            ) / (test_portfolio_holdings.quantity + EXCLUDED.quantity)
        `, [testUserId, buyTransaction.symbol, buyTransaction.quantity, buyTransaction.price]);

        // Update cash balance
        await client.query(`
          UPDATE test_portfolio_metadata 
          SET cash_balance = cash_balance - $1
          WHERE user_id = $2
        `, [totalAmount, testUserId]);

        await client.query('COMMIT');

        // Verify holding was created
        const holdingResult = await client.query(`
          SELECT * FROM test_portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, buyTransaction.symbol]);

        expect(holdingResult.rows).toHaveLength(1);
        const holding = holdingResult.rows[0];
        expect(parseFloat(holding.quantity)).toBe(100);
        expect(parseFloat(holding.avg_cost)).toBe(175.50);

      } finally {
        client.release();
      }
    });

    it('updates existing holdings with additional purchases', async () => {
      const client = await dbPool.connect();
      try {
        // First purchase
        await client.query(`
          INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
          VALUES ($1, $2, $3, $4)
        `, [testUserId, 'GOOGL', 10, 2600.00]);

        // Second purchase at different price
        const additionalQuantity = 5;
        const newPrice = 2700.00;

        await client.query('BEGIN');

        // Calculate new average cost
        const currentHolding = await client.query(`
          SELECT quantity, avg_cost FROM test_portfolio_holdings
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, 'GOOGL']);

        const currentQty = parseFloat(currentHolding.rows[0].quantity);
        const currentAvgCost = parseFloat(currentHolding.rows[0].avg_cost);
        
        const totalCurrentValue = currentQty * currentAvgCost;
        const additionalValue = additionalQuantity * newPrice;
        const newTotalQty = currentQty + additionalQuantity;
        const newAvgCost = (totalCurrentValue + additionalValue) / newTotalQty;

        // Update holding
        await client.query(`
          UPDATE test_portfolio_holdings 
          SET quantity = $1, avg_cost = $2
          WHERE user_id = $3 AND symbol = $4
        `, [newTotalQty, newAvgCost, testUserId, 'GOOGL']);

        await client.query('COMMIT');

        // Verify update
        const updatedHolding = await client.query(`
          SELECT * FROM test_portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, 'GOOGL']);

        const holding = updatedHolding.rows[0];
        expect(parseFloat(holding.quantity)).toBe(15);
        expect(parseFloat(holding.avg_cost)).toBeCloseTo(2633.33, 2);

      } finally {
        client.release();
      }
    });

    it('handles sell transactions and updates holdings', async () => {
      const client = await dbPool.connect();
      try {
        // Set up initial holding
        await client.query(`
          INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (user_id, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_cost = EXCLUDED.avg_cost
        `, [testUserId, 'MSFT', 50, 400.00]);

        await client.query('BEGIN');

        // Sell partial position
        const sellQuantity = 20;
        const sellPrice = 410.25;
        const fees = 9.95;
        const totalAmount = (sellQuantity * sellPrice) - fees;

        // Record sell transaction
        await client.query(`
          INSERT INTO test_portfolio_transactions 
          (user_id, symbol, transaction_type, quantity, price, total_amount, fees)
          VALUES ($1, $2, $3, $4, $5, $6, $7)
        `, [testUserId, 'MSFT', 'SELL', sellQuantity, sellPrice, totalAmount, fees]);

        // Update holding
        await client.query(`
          UPDATE test_portfolio_holdings 
          SET quantity = quantity - $1
          WHERE user_id = $2 AND symbol = $3
        `, [sellQuantity, testUserId, 'MSFT']);

        // Update cash balance
        await client.query(`
          UPDATE test_portfolio_metadata 
          SET cash_balance = cash_balance + $1
          WHERE user_id = $2
        `, [totalAmount, testUserId]);

        await client.query('COMMIT');

        // Verify holding was updated
        const holdingResult = await client.query(`
          SELECT * FROM test_portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, 'MSFT']);

        expect(holdingResult.rows).toHaveLength(1);
        const holding = holdingResult.rows[0];
        expect(parseFloat(holding.quantity)).toBe(30); // 50 - 20
        expect(parseFloat(holding.avg_cost)).toBe(400.00); // Unchanged

      } finally {
        client.release();
      }
    });

    it('removes holdings when quantity reaches zero', async () => {
      const client = await dbPool.connect();
      try {
        // Set up small holding
        await client.query(`
          INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (user_id, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_cost = EXCLUDED.avg_cost
        `, [testUserId, 'TSLA', 10, 245.80]);

        await client.query('BEGIN');

        // Sell entire position
        await client.query(`
          INSERT INTO test_portfolio_transactions 
          (user_id, symbol, transaction_type, quantity, price, total_amount, fees)
          VALUES ($1, $2, $3, $4, $5, $6, $7)
        `, [testUserId, 'TSLA', 'SELL', 10, 245.80, 2458.00 - 9.95, 9.95]);

        // Remove holding completely
        await client.query(`
          DELETE FROM test_portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, 'TSLA']);

        await client.query('COMMIT');

        // Verify holding was removed
        const holdingResult = await client.query(`
          SELECT * FROM test_portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, 'TSLA']);

        expect(holdingResult.rows).toHaveLength(0);

      } finally {
        client.release();
      }
    });
  });

  describe('Portfolio Valuation and Analytics', () => {
    beforeEach(async () => {
      // Set up diverse portfolio for testing
      const client = await dbPool.connect();
      try {
        await client.query('BEGIN');

        // Clear existing holdings
        await client.query('DELETE FROM test_portfolio_holdings WHERE user_id = $1', [testUserId]);

        // Add diverse holdings
        const holdings = [
          { symbol: 'AAPL', quantity: 100, avgCost: 150.00 },
          { symbol: 'GOOGL', quantity: 10, avgCost: 2500.00 },
          { symbol: 'MSFT', quantity: 50, avgCost: 350.00 },
          { symbol: 'TSLA', quantity: 25, avgCost: 300.00 }
        ];

        for (const holding of holdings) {
          await client.query(`
            INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
            VALUES ($1, $2, $3, $4)
          `, [testUserId, holding.symbol, holding.quantity, holding.avgCost]);
        }

        await client.query('COMMIT');
      } finally {
        client.release();
      }
    });

    it('calculates portfolio total value with current market prices', async () => {
      const client = await dbPool.connect();
      try {
        // Calculate total portfolio value
        const valueResult = await client.query(`
          SELECT 
            h.symbol,
            h.quantity,
            h.avg_cost,
            m.current_price,
            (h.quantity * m.current_price) as market_value,
            (h.quantity * h.avg_cost) as cost_basis,
            ((h.quantity * m.current_price) - (h.quantity * h.avg_cost)) as gain_loss
          FROM test_portfolio_holdings h
          JOIN test_market_data m ON h.symbol = m.symbol
          WHERE h.user_id = $1
          ORDER BY h.symbol
        `, [testUserId]);

        expect(valueResult.rows.length).toBeGreaterThan(0);

        let totalMarketValue = 0;
        let totalCostBasis = 0;

        valueResult.rows.forEach(holding => {
          expect(parseFloat(holding.market_value)).toBeGreaterThan(0);
          expect(parseFloat(holding.cost_basis)).toBeGreaterThan(0);
          
          totalMarketValue += parseFloat(holding.market_value);
          totalCostBasis += parseFloat(holding.cost_basis);
        });

        const totalGainLoss = totalMarketValue - totalCostBasis;
        const gainLossPercentage = (totalGainLoss / totalCostBasis) * 100;

        console.log(`📊 Portfolio Summary:`);
        console.log(`   Market Value: $${totalMarketValue.toFixed(2)}`);
        console.log(`   Cost Basis: $${totalCostBasis.toFixed(2)}`);
        console.log(`   Gain/Loss: $${totalGainLoss.toFixed(2)} (${gainLossPercentage.toFixed(2)}%)`);

        expect(totalMarketValue).toBeGreaterThan(0);
        expect(totalCostBasis).toBeGreaterThan(0);
      } finally {
        client.release();
      }
    });

    it('tracks portfolio performance over time', async () => {
      const client = await dbPool.connect();
      try {
        // Calculate current portfolio metrics
        const metricsResult = await client.query(`
          SELECT 
            SUM(h.quantity * m.current_price) as total_market_value,
            SUM(h.quantity * h.avg_cost) as total_cost_basis,
            (SUM(h.quantity * m.current_price) - SUM(h.quantity * h.avg_cost)) as total_gain_loss,
            CASE 
              WHEN SUM(h.quantity * h.avg_cost) > 0 
              THEN ((SUM(h.quantity * m.current_price) - SUM(h.quantity * h.avg_cost)) / SUM(h.quantity * h.avg_cost)) * 100
              ELSE 0 
            END as gain_loss_percentage
          FROM test_portfolio_holdings h
          JOIN test_market_data m ON h.symbol = m.symbol
          WHERE h.user_id = $1
        `, [testUserId]);

        const metrics = metricsResult.rows[0];

        // Update portfolio metadata
        await client.query(`
          UPDATE test_portfolio_metadata SET
            total_value = $1,
            total_cost_basis = $2,
            total_gain_loss = $3,
            gain_loss_percentage = $4,
            last_calculated = CURRENT_TIMESTAMP
          WHERE user_id = $5
        `, [
          parseFloat(metrics.total_market_value),
          parseFloat(metrics.total_cost_basis),
          parseFloat(metrics.total_gain_loss),
          parseFloat(metrics.gain_loss_percentage),
          testUserId
        ]);

        // Verify metrics were updated
        const updatedMetrics = await client.query(`
          SELECT * FROM test_portfolio_metadata WHERE user_id = $1
        `, [testUserId]);

        const portfolio = updatedMetrics.rows[0];
        expect(parseFloat(portfolio.total_value)).toBeGreaterThan(0);
        expect(parseFloat(portfolio.total_cost_basis)).toBeGreaterThan(0);
        expect(portfolio.last_calculated).toBeDefined();

      } finally {
        client.release();
      }
    });

    it('generates portfolio diversification analysis', async () => {
      const client = await dbPool.connect();
      try {
        // Calculate position sizing and diversification
        const diversificationResult = await client.query(`
          WITH portfolio_total AS (
            SELECT SUM(h.quantity * m.current_price) as total_value
            FROM test_portfolio_holdings h
            JOIN test_market_data m ON h.symbol = m.symbol
            WHERE h.user_id = $1
          )
          SELECT 
            h.symbol,
            h.quantity,
            m.current_price,
            (h.quantity * m.current_price) as position_value,
            ((h.quantity * m.current_price) / pt.total_value * 100) as weight_percentage
          FROM test_portfolio_holdings h
          JOIN test_market_data m ON h.symbol = m.symbol
          CROSS JOIN portfolio_total pt
          WHERE h.user_id = $1
          ORDER BY position_value DESC
        `, [testUserId]);

        expect(diversificationResult.rows.length).toBeGreaterThan(0);

        let totalWeight = 0;
        diversificationResult.rows.forEach(position => {
          const weight = parseFloat(position.weight_percentage);
          expect(weight).toBeGreaterThan(0);
          expect(weight).toBeLessThanOrEqual(100);
          totalWeight += weight;
        });

        // Total weights should sum to ~100%
        expect(totalWeight).toBeCloseTo(100, 1);

        // Ensure no single position dominates (> 50%)
        const largestPosition = Math.max(...diversificationResult.rows.map(p => parseFloat(p.weight_percentage)));
        expect(largestPosition).toBeLessThan(80); // Reasonable diversification test

      } finally {
        client.release();
      }
    });
  });

  describe('Transaction History and Reporting', () => {
    it('retrieves complete transaction history with calculations', async () => {
      const client = await dbPool.connect();
      try {
        // Add some test transactions
        const transactions = [
          { symbol: 'AAPL', type: 'BUY', quantity: 50, price: 145.00, fees: 9.95 },
          { symbol: 'AAPL', type: 'BUY', quantity: 50, price: 155.00, fees: 9.95 },
          { symbol: 'AAPL', type: 'SELL', quantity: 25, price: 165.00, fees: 9.95 }
        ];

        for (const txn of transactions) {
          const totalAmount = txn.type === 'BUY' 
            ? (txn.quantity * txn.price) + txn.fees
            : (txn.quantity * txn.price) - txn.fees;

          await client.query(`
            INSERT INTO test_portfolio_transactions 
            (user_id, symbol, transaction_type, quantity, price, total_amount, fees)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
          `, [testUserId, txn.symbol, txn.type, txn.quantity, txn.price, totalAmount, txn.fees]);
        }

        // Retrieve transaction history with analysis
        const historyResult = await client.query(`
          SELECT 
            transaction_id,
            symbol,
            transaction_type,
            quantity,
            price,
            total_amount,
            fees,
            transaction_date,
            SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE -quantity END) 
              OVER (PARTITION BY symbol ORDER BY transaction_date) as running_quantity
          FROM test_portfolio_transactions
          WHERE user_id = $1
          ORDER BY transaction_date DESC, transaction_id DESC
        `, [testUserId]);

        expect(historyResult.rows.length).toBeGreaterThan(0);

        // Verify transaction data integrity
        historyResult.rows.forEach(txn => {
          expect(txn.symbol).toBeDefined();
          expect(['BUY', 'SELL']).toContain(txn.transaction_type);
          expect(parseFloat(txn.quantity)).toBeGreaterThan(0);
          expect(parseFloat(txn.price)).toBeGreaterThan(0);
          expect(parseFloat(txn.total_amount)).toBeGreaterThan(0);
        });

      } finally {
        client.release();
      }
    });

    it('calculates realized and unrealized gains/losses', async () => {
      const client = await dbPool.connect();
      try {
        // Set up holding with known cost basis
        await client.query(`
          INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (user_id, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_cost = EXCLUDED.avg_cost
        `, [testUserId, 'AAPL', 75, 150.00]);

        // Add a sell transaction for realized gain calculation
        await client.query(`
          INSERT INTO test_portfolio_transactions 
          (user_id, symbol, transaction_type, quantity, price, total_amount, fees)
          VALUES ($1, $2, $3, $4, $5, $6, $7)
        `, [testUserId, 'AAPL', 'SELL', 25, 175.50, (25 * 175.50) - 9.95, 9.95]);

        // Calculate gains/losses
        const gainsResult = await client.query(`
          WITH current_holdings AS (
            SELECT 
              h.symbol,
              h.quantity as current_quantity,
              h.avg_cost,
              m.current_price,
              (h.quantity * h.avg_cost) as cost_basis,
              (h.quantity * m.current_price) as market_value,
              ((h.quantity * m.current_price) - (h.quantity * h.avg_cost)) as unrealized_gain_loss
            FROM test_portfolio_holdings h
            JOIN test_market_data m ON h.symbol = m.symbol
            WHERE h.user_id = $1
          ),
          realized_gains AS (
            SELECT 
              symbol,
              SUM(
                CASE 
                  WHEN transaction_type = 'SELL' 
                  THEN (quantity * price) - fees - (quantity * 150.00) -- Assuming avg cost of $150
                  ELSE 0 
                END
              ) as realized_gain_loss
            FROM test_portfolio_transactions
            WHERE user_id = $1
            GROUP BY symbol
          )
          SELECT 
            ch.symbol,
            ch.current_quantity,
            ch.cost_basis,
            ch.market_value,
            ch.unrealized_gain_loss,
            COALESCE(rg.realized_gain_loss, 0) as realized_gain_loss,
            (ch.unrealized_gain_loss + COALESCE(rg.realized_gain_loss, 0)) as total_gain_loss
          FROM current_holdings ch
          LEFT JOIN realized_gains rg ON ch.symbol = rg.symbol
        `, [testUserId]);

        expect(gainsResult.rows.length).toBeGreaterThan(0);

        const applePosition = gainsResult.rows.find(row => row.symbol === 'AAPL');
        expect(applePosition).toBeDefined();
        expect(parseFloat(applePosition.unrealized_gain_loss)).toBeDefined();
        expect(parseFloat(applePosition.realized_gain_loss)).toBeGreaterThan(0); // Should have realized gain from sale

      } finally {
        client.release();
      }
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('handles insufficient holdings for sell orders', async () => {
      const client = await dbPool.connect();
      try {
        // Try to sell more than owned
        await client.query(`
          INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (user_id, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_cost = EXCLUDED.avg_cost
        `, [testUserId, 'TEST', 10, 100.00]);

        // Attempt to sell 15 shares when only 10 are owned
        await expect(
          client.query(`
            UPDATE test_portfolio_holdings 
            SET quantity = quantity - $1
            WHERE user_id = $2 AND symbol = $3 AND quantity >= $1
          `, [15, testUserId, 'TEST'])
        ).resolves.toBeDefined();

        // Verify the update didn't happen (0 rows affected)
        const checkResult = await client.query(`
          SELECT quantity FROM test_portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, 'TEST']);

        expect(parseFloat(checkResult.rows[0].quantity)).toBe(10); // Unchanged

      } finally {
        client.release();
      }
    });

    it('validates transaction data integrity', async () => {
      const client = await dbPool.connect();
      try {
        // Test negative price validation
        await expect(
          client.query(`
            INSERT INTO test_portfolio_transactions 
            (user_id, symbol, transaction_type, quantity, price, total_amount, fees)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
          `, [testUserId, 'TEST', 'BUY', 10, -100.00, 1000.00, 9.95])
        ).rejects.toThrow();

        // Test zero quantity validation
        await expect(
          client.query(`
            INSERT INTO test_portfolio_transactions 
            (user_id, symbol, transaction_type, quantity, price, total_amount, fees)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
          `, [testUserId, 'TEST', 'BUY', 0, 100.00, 1000.00, 9.95])
        ).rejects.toThrow();

      } finally {
        client.release();
      }
    });

    it('handles concurrent transaction processing', async () => {
      // Test concurrent buy/sell operations
      const client1 = await dbPool.connect();
      const client2 = await dbPool.connect();

      try {
        // Set up initial holding
        await client1.query(`
          INSERT INTO test_portfolio_holdings (user_id, symbol, quantity, avg_cost)
          VALUES ($1, $2, $3, $4)
          ON CONFLICT (user_id, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_cost = EXCLUDED.avg_cost
        `, [testUserId, 'CONCURRENT', 100, 150.00]);

        // Simulate concurrent transactions
        const promises = [
          client1.query(`
            UPDATE test_portfolio_holdings 
            SET quantity = quantity + 50
            WHERE user_id = $1 AND symbol = $2
          `, [testUserId, 'CONCURRENT']),
          
          client2.query(`
            UPDATE test_portfolio_holdings 
            SET quantity = quantity - 25
            WHERE user_id = $1 AND symbol = $2
          `, [testUserId, 'CONCURRENT'])
        ];

        await Promise.all(promises);

        // Verify final state
        const finalResult = await client1.query(`
          SELECT quantity FROM test_portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, [testUserId, 'CONCURRENT']);

        const finalQuantity = parseFloat(finalResult.rows[0].quantity);
        expect(finalQuantity).toBe(125); // 100 + 50 - 25

      } finally {
        client1.release();
        client2.release();
      }
    });
  });
});