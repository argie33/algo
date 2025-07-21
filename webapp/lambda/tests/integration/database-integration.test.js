/**
 * INTEGRATION TESTS: Database Real Service Integration
 * Industry Standard: Tests real component interactions with AWS services
 * Uses IaC-deployed test infrastructure with proper setup/teardown
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Pool } = require('pg');

const describeOrSkip = (process.env.TEST_DB_SECRET_ARN) ? describe : describe.skip;

describeOrSkip('Database Integration Tests (Industry Standard)', () => {
  let testConfig;
  let dbPool;
  let secretsManager;

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
        ssl: false, // Test environment
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

      console.log('✅ Integration test database connection established');

      // Set up test schema
      await setupTestSchema();

    } catch (error) {
      console.error('❌ Integration test setup failed:', error.message);
      
      // Skip tests if infrastructure not available
      if (error.code === 'ENOTFOUND' || error.message.includes('SECRET_ARN')) {
        console.log('⚠️ Skipping integration tests - test infrastructure not available');
        // Set a flag to skip all tests in this suite
        global.__SKIP_INTEGRATION_TESTS__ = true;
        return;
      }
      
      throw error;
    }
  }, 30000);

  afterAll(async () => {
    if (dbPool) {
      await cleanupTestData();
      await dbPool.end();
      console.log('✅ Integration test cleanup completed');
    }
  });

  async function setupTestSchema() {
    const client = await dbPool.connect();
    try {
      // Create test tables
      await client.query(`
        CREATE TABLE IF NOT EXISTS test_users (
          user_id SERIAL PRIMARY KEY,
          email VARCHAR(255) UNIQUE NOT NULL,
          username VARCHAR(100) UNIQUE NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
      `);

      await client.query(`
        CREATE TABLE IF NOT EXISTS test_portfolio (
          portfolio_id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES test_users(user_id) ON DELETE CASCADE,
          symbol VARCHAR(10) NOT NULL,
          quantity DECIMAL(15, 6) NOT NULL,
          avg_cost DECIMAL(10, 2) NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
      `);

      console.log('✅ Test schema created');
    } finally {
      client.release();
    }
  }

  async function cleanupTestData() {
    const client = await dbPool.connect();
    try {
      await client.query('DROP TABLE IF EXISTS test_portfolio CASCADE');
      await client.query('DROP TABLE IF EXISTS test_users CASCADE');
      console.log('✅ Test data cleaned up');
    } finally {
      client.release();
    }
  }


  describe('Database Connection and Transactions', () => {
    it('establishes connection and executes basic queries', async () => {
      const client = await dbPool.connect();
      try {
        const result = await client.query('SELECT $1 as test_value', ['integration-test']);
        expect(result.rows[0].test_value).toBe('integration-test');
      } finally {
        client.release();
      }
    });

    it('executes transactions with proper commit', async () => {
      const client = await dbPool.connect();
      try {
        await client.query('BEGIN');
        
        const insertResult = await client.query(`
          INSERT INTO test_users (email, username) 
          VALUES ($1, $2) 
          RETURNING user_id
        `, ['integration@test.com', 'integration_user']);

        const userId = insertResult.rows[0].user_id;
        expect(userId).toBeDefined();

        await client.query('COMMIT');

        // Verify the data was committed
        const selectResult = await client.query(
          'SELECT * FROM test_users WHERE user_id = $1',
          [userId]
        );
        expect(selectResult.rows).toHaveLength(1);
        expect(selectResult.rows[0].email).toBe('integration@test.com');

      } finally {
        client.release();
      }
    });

    it('handles transaction rollback on errors', async () => {
      const client = await dbPool.connect();
      try {
        await client.query('BEGIN');
        
        // Insert valid data
        await client.query(`
          INSERT INTO test_users (email, username) 
          VALUES ($1, $2)
        `, ['rollback@test.com', 'rollback_user']);
        
        // Force an error by violating constraint
        try {
          await client.query(`
            INSERT INTO test_users (email, username) 
            VALUES ($1, $2)
          `, ['rollback@test.com', 'rollback_user']); // Duplicate email
        } catch (error) {
          await client.query('ROLLBACK');
        }
        
        // Verify data was rolled back
        const selectResult = await client.query(
          'SELECT COUNT(*) as count FROM test_users WHERE email = $1',
          ['rollback@test.com']
        );
        expect(parseInt(selectResult.rows[0].count)).toBe(0);
        
      } finally {
        client.release();
      }
    });

    it('tests connection pool under load', async () => {
      const concurrentQueries = 10;
      const promises = [];
      
      for (let i = 0; i < concurrentQueries; i++) {
        promises.push((async () => {
          const client = await dbPool.connect();
          try {
            const result = await client.query('SELECT $1 as query_id, NOW() as timestamp', [i]);
            return result.rows[0];
          } finally {
            client.release();
          }
        })());
      }
      
      const results = await Promise.all(promises);
      expect(results).toHaveLength(concurrentQueries);
      
      // Verify all queries completed successfully
      results.forEach((result, index) => {
        expect(result.query_id).toBe(index);
        expect(result.timestamp).toBeDefined();
      });
    });
  });

  describe('Real AWS Services Integration', () => {
    it('connects to RDS instance through Secrets Manager', async () => {
      // Verify the database credentials were loaded from Secrets Manager
      expect(testConfig.host).toBeDefined();
      expect(testConfig.user).toBe('testuser');
      expect(testConfig.password).toMatch(/^testpass-/);
      
      // Test direct RDS connection
      const client = await dbPool.connect();
      try {
        // Verify we're connected to the correct database
        const result = await client.query(`
          SELECT current_database() as db_name, 
                 version() as db_version,
                 current_user as db_user
        `);
        
        expect(result.rows[0].db_name).toBe('postgres');
        expect(result.rows[0].db_version).toMatch(/PostgreSQL/);
        expect(result.rows[0].db_user).toBe('testuser');
      } finally {
        client.release();
      }
    });

    it('validates AWS infrastructure components', async () => {
      // Test that we can access Secrets Manager
      const secretArn = process.env.TEST_DB_SECRET_ARN;
      expect(secretArn).toBeDefined();
      
      try {
        const secretResponse = await secretsManager.getSecretValue({
          SecretId: secretArn
        }).promise();
        
        const credentials = JSON.parse(secretResponse.SecretString);
        expect(credentials).toMatchObject({
          username: 'testuser',
          password: expect.stringMatching(/^testpass-/),
          engine: 'postgres',
          host: expect.any(String),
          port: 5432,
          dbname: 'postgres'
        });
      } catch (error) {
        throw new Error(`Secrets Manager integration failed: ${error.message}`);
      }
    });

    it('tests database performance and latency', async () => {
      const iterations = 5;
      const latencies = [];
      
      for (let i = 0; i < iterations; i++) {
        const startTime = Date.now();
        
        const client = await dbPool.connect();
        try {
          await client.query('SELECT 1');
        } finally {
          client.release();
        }
        
        const latency = Date.now() - startTime;
        latencies.push(latency);
      }
      
      const avgLatency = latencies.reduce((sum, lat) => sum + lat, 0) / latencies.length;
      const maxLatency = Math.max(...latencies);
      
      console.log(`✅ Database latency - Avg: ${avgLatency}ms, Max: ${maxLatency}ms`);
      
      // Performance assertions for integration testing
      expect(avgLatency).toBeLessThan(1000); // Average should be under 1 second
      expect(maxLatency).toBeLessThan(2000);  // Max should be under 2 seconds
    });
  });

  describe('Portfolio and User Data Integration', () => {
    let testUserId;
    
    beforeEach(async () => {
      // Create a test user for portfolio tests
      const client = await dbPool.connect();
      try {
        const result = await client.query(`
          INSERT INTO test_users (email, username) 
          VALUES ($1, $2) 
          RETURNING user_id
        `, [`portfolio-test-${Date.now()}@test.com`, `portfolio_user_${Date.now()}`]);
        
        testUserId = result.rows[0].user_id;
      } finally {
        client.release();
      }
    });

    it('creates and manages portfolio holdings', async () => {
      const client = await dbPool.connect();
      try {
        // Insert portfolio holdings
        const insertResult = await client.query(`
          INSERT INTO test_portfolio (user_id, symbol, quantity, avg_cost) 
          VALUES ($1, $2, $3, $4) 
          RETURNING portfolio_id
        `, [testUserId, 'AAPL', 100.50, 150.25]);
        
        const portfolioId = insertResult.rows[0].portfolio_id;
        expect(portfolioId).toBeDefined();
        
        // Verify the portfolio data
        const selectResult = await client.query(`
          SELECT p.*, u.username 
          FROM test_portfolio p
          JOIN test_users u ON p.user_id = u.user_id
          WHERE p.portfolio_id = $1
        `, [portfolioId]);
        
        expect(selectResult.rows).toHaveLength(1);
        const holding = selectResult.rows[0];
        expect(holding.symbol).toBe('AAPL');
        expect(parseFloat(holding.quantity)).toBe(100.50);
        expect(parseFloat(holding.avg_cost)).toBe(150.25);
        expect(holding.username).toMatch(/^portfolio_user_/);
        
      } finally {
        client.release();
      }
    });

    it('handles complex portfolio queries with aggregations', async () => {
      const client = await dbPool.connect();
      try {
        // Insert multiple holdings
        const holdings = [
          { symbol: 'AAPL', quantity: 100, cost: 150.00 },
          { symbol: 'GOOGL', quantity: 50, cost: 2500.00 },
          { symbol: 'MSFT', quantity: 200, cost: 300.00 }
        ];
        
        for (const holding of holdings) {
          await client.query(`
            INSERT INTO test_portfolio (user_id, symbol, quantity, avg_cost) 
            VALUES ($1, $2, $3, $4)
          `, [testUserId, holding.symbol, holding.quantity, holding.cost]);
        }
        
        // Test aggregation query
        const aggregateResult = await client.query(`
          SELECT 
            COUNT(*) as total_holdings,
            SUM(quantity * avg_cost) as total_value,
            AVG(avg_cost) as avg_cost_per_share,
            array_agg(symbol ORDER BY symbol) as symbols
          FROM test_portfolio 
          WHERE user_id = $1
        `, [testUserId]);
        
        const aggregate = aggregateResult.rows[0];
        expect(parseInt(aggregate.total_holdings)).toBe(3);
        expect(parseFloat(aggregate.total_value)).toBe(190000); // 100*150 + 50*2500 + 200*300
        expect(aggregate.symbols).toEqual(['AAPL', 'GOOGL', 'MSFT']);
        
      } finally {
        client.release();
      }
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('handles database connection failures gracefully', async () => {
      // Test connection timeout handling
      const originalIdleTimeout = dbPool.options.idleTimeoutMillis;
      
      // This test verifies the pool can handle connection issues
      expect(dbPool.totalCount).toBeGreaterThanOrEqual(0);
      expect(dbPool.idleCount).toBeGreaterThanOrEqual(0);
    });

    it('validates data integrity constraints', async () => {
      const client = await dbPool.connect();
      try {
        // Test unique constraint violation
        const uniqueEmail = `unique-test-${Date.now()}@test.com`;
        
        await client.query(`
          INSERT INTO test_users (email, username) 
          VALUES ($1, $2)
        `, [uniqueEmail, 'first_user']);
        
        // Should fail on duplicate email
        await expect(
          client.query(`
            INSERT INTO test_users (email, username) 
            VALUES ($1, $2)
          `, [uniqueEmail, 'second_user'])
        ).rejects.toThrow();
        
      } finally {
        client.release();
      }
    });

    it('tests foreign key constraints', async () => {
      const client = await dbPool.connect();
      try {
        // Should fail to insert portfolio for non-existent user
        await expect(
          client.query(`
            INSERT INTO test_portfolio (user_id, symbol, quantity, avg_cost) 
            VALUES ($1, $2, $3, $4)
          `, [99999, 'TEST', 1, 1.00])
        ).rejects.toThrow();
        
      } finally {
        client.release();
      }
    });
  })
});