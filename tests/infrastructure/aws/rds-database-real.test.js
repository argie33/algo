/**
 * AWS RDS Database Real Integration Tests
 * Tests actual RDS database connectivity and operations
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import mysql from 'mysql2/promise';
import { RDSClient, DescribeDBInstancesCommand } from '@aws-sdk/client-rds';

// Database configuration from environment
const DB_CONFIG = {
  host: process.env.RDS_ENDPOINT || 'localhost',
  port: process.env.RDS_PORT || 3306,
  user: process.env.RDS_USERNAME || 'admin',
  password: process.env.RDS_PASSWORD || 'password',
  database: process.env.RDS_DATABASE || 'financial_platform',
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false
};

// AWS RDS Client configuration
const AWS_REGION = process.env.AWS_REGION || 'us-east-1';
const RDS_INSTANCE_ID = process.env.RDS_INSTANCE_ID;

describe('AWS RDS Database Real Integration Tests', () => {
  let connection;
  let rdsClient;

  beforeAll(async () => {
    // Skip tests if database configuration not available
    if (!process.env.RDS_ENDPOINT) {
      console.warn('⚠️ Skipping RDS tests - Database configuration missing');
      return;
    }

    try {
      // Initialize RDS client for infrastructure checks
      rdsClient = new RDSClient({
        region: AWS_REGION,
        credentials: {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID,
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY
        }
      });

      // Test database connection
      connection = await mysql.createConnection(DB_CONFIG);
      console.log('✅ Connected to RDS database');

      // Create test tables if they don't exist
      await setupTestTables(connection);
      
    } catch (error) {
      console.error('❌ Failed to connect to RDS:', error.message);
      throw new Error('RDS connection failed - check database configuration');
    }
  });

  afterAll(async () => {
    if (connection) {
      try {
        // Clean up test data
        await cleanupTestTables(connection);
        await connection.end();
        console.log('🧹 Database connection closed');
      } catch (error) {
        console.warn('⚠️ Error during cleanup:', error.message);
      }
    }
  });

  beforeEach(async () => {
    if (!connection) return;
    // Clear test data before each test
    await connection.execute('DELETE FROM test_portfolios WHERE user_id LIKE "test_%"');
    await connection.execute('DELETE FROM test_holdings WHERE portfolio_id IN (SELECT id FROM test_portfolios WHERE user_id LIKE "test_%")');
    await connection.execute('DELETE FROM test_transactions WHERE portfolio_id IN (SELECT id FROM test_portfolios WHERE user_id LIKE "test_%")');
  });

  describe('Database Connectivity', () => {
    it('establishes connection to RDS instance', async () => {
      if (!connection) return;

      const [rows] = await connection.execute('SELECT 1 as connected');
      expect(rows[0].connected).toBe(1);
    });

    it('validates database schema exists', async () => {
      if (!connection) return;

      const [rows] = await connection.execute('SELECT DATABASE() as db_name');
      expect(rows[0].db_name).toBe(DB_CONFIG.database);
    });

    it('verifies required tables exist', async () => {
      if (!connection) return;

      const requiredTables = ['test_portfolios', 'test_holdings', 'test_transactions'];
      
      for (const table of requiredTables) {
        const [rows] = await connection.execute(
          'SELECT COUNT(*) as table_exists FROM information_schema.tables WHERE table_schema = ? AND table_name = ?',
          [DB_CONFIG.database, table]
        );
        expect(rows[0].table_exists).toBe(1);
      }
    });

    it('tests database performance', async () => {
      if (!connection) return;

      const startTime = Date.now();
      await connection.execute('SELECT COUNT(*) FROM test_portfolios');
      const responseTime = Date.now() - startTime;

      // Database should respond within reasonable time
      expect(responseTime).toBeLessThan(1000); // 1 second
      console.log(`⏱️ Database response time: ${responseTime}ms`);
    });
  });

  describe('Portfolio Data Operations', () => {
    let testUserId;
    let testPortfolioId;

    beforeEach(() => {
      testUserId = `test_user_${Date.now()}`;
    });

    it('creates portfolio record', async () => {
      if (!connection) return;

      const portfolioData = {
        user_id: testUserId,
        name: 'Test Growth Portfolio',
        description: 'Integration test portfolio',
        risk_level: 'moderate',
        target_allocation: JSON.stringify({ stocks: 70, bonds: 20, cash: 10 }),
        created_at: new Date()
      };

      const [result] = await connection.execute(
        'INSERT INTO test_portfolios (user_id, name, description, risk_level, target_allocation, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        [portfolioData.user_id, portfolioData.name, portfolioData.description, portfolioData.risk_level, portfolioData.target_allocation, portfolioData.created_at]
      );

      testPortfolioId = result.insertId;
      expect(result.insertId).toBeGreaterThan(0);
      expect(result.affectedRows).toBe(1);
    });

    it('retrieves portfolio by ID', async () => {
      if (!connection || !testPortfolioId) return;

      const [rows] = await connection.execute(
        'SELECT * FROM test_portfolios WHERE id = ?',
        [testPortfolioId]
      );

      expect(rows).toHaveLength(1);
      expect(rows[0].name).toBe('Test Growth Portfolio');
      expect(rows[0].user_id).toBe(testUserId);
      expect(rows[0].risk_level).toBe('moderate');
    });

    it('updates portfolio data', async () => {
      if (!connection || !testPortfolioId) return;

      const newName = 'Updated Portfolio Name';
      const newRiskLevel = 'aggressive';

      const [result] = await connection.execute(
        'UPDATE test_portfolios SET name = ?, risk_level = ?, updated_at = NOW() WHERE id = ?',
        [newName, newRiskLevel, testPortfolioId]
      );

      expect(result.affectedRows).toBe(1);

      // Verify update
      const [rows] = await connection.execute(
        'SELECT name, risk_level FROM test_portfolios WHERE id = ?',
        [testPortfolioId]
      );

      expect(rows[0].name).toBe(newName);
      expect(rows[0].risk_level).toBe(newRiskLevel);
    });

    it('deletes portfolio and cascades to holdings', async () => {
      if (!connection || !testPortfolioId) return;

      // First add a holding
      await connection.execute(
        'INSERT INTO test_holdings (portfolio_id, symbol, quantity, avg_cost_basis, current_price) VALUES (?, ?, ?, ?, ?)',
        [testPortfolioId, 'AAPL', 100, 150.00, 155.00]
      );

      // Delete portfolio
      const [deleteResult] = await connection.execute(
        'DELETE FROM test_portfolios WHERE id = ?',
        [testPortfolioId]
      );

      expect(deleteResult.affectedRows).toBe(1);

      // Verify portfolio is deleted
      const [portfolioRows] = await connection.execute(
        'SELECT * FROM test_portfolios WHERE id = ?',
        [testPortfolioId]
      );
      expect(portfolioRows).toHaveLength(0);

      // Verify holdings are also deleted (assuming CASCADE DELETE)
      const [holdingRows] = await connection.execute(
        'SELECT * FROM test_holdings WHERE portfolio_id = ?',
        [testPortfolioId]
      );
      expect(holdingRows).toHaveLength(0);
    });
  });

  describe('Holdings Management', () => {
    let testPortfolioId;

    beforeEach(async () => {
      if (!connection) return;

      // Create test portfolio
      const [result] = await connection.execute(
        'INSERT INTO test_portfolios (user_id, name, created_at) VALUES (?, ?, ?)',
        [`test_user_${Date.now()}`, 'Test Portfolio', new Date()]
      );
      testPortfolioId = result.insertId;
    });

    it('adds stock holding to portfolio', async () => {
      if (!connection || !testPortfolioId) return;

      const holdingData = {
        portfolio_id: testPortfolioId,
        symbol: 'AAPL',
        quantity: 100,
        avg_cost_basis: 150.00,
        current_price: 155.00,
        sector: 'Technology'
      };

      const [result] = await connection.execute(
        'INSERT INTO test_holdings (portfolio_id, symbol, quantity, avg_cost_basis, current_price, sector) VALUES (?, ?, ?, ?, ?, ?)',
        [holdingData.portfolio_id, holdingData.symbol, holdingData.quantity, holdingData.avg_cost_basis, holdingData.current_price, holdingData.sector]
      );

      expect(result.insertId).toBeGreaterThan(0);
      expect(result.affectedRows).toBe(1);
    });

    it('calculates portfolio value from holdings', async () => {
      if (!connection || !testPortfolioId) return;

      // Add multiple holdings
      const holdings = [
        { symbol: 'AAPL', quantity: 100, price: 155.00 },
        { symbol: 'GOOGL', quantity: 50, price: 2600.00 },
        { symbol: 'MSFT', quantity: 75, price: 380.00 }
      ];

      for (const holding of holdings) {
        await connection.execute(
          'INSERT INTO test_holdings (portfolio_id, symbol, quantity, current_price) VALUES (?, ?, ?, ?)',
          [testPortfolioId, holding.symbol, holding.quantity, holding.price]
        );
      }

      // Calculate total portfolio value
      const [rows] = await connection.execute(`
        SELECT 
          SUM(quantity * current_price) as total_value,
          COUNT(*) as holdings_count
        FROM test_holdings 
        WHERE portfolio_id = ?
      `, [testPortfolioId]);

      const expectedValue = (100 * 155) + (50 * 2600) + (75 * 380); // $173,500
      expect(rows[0].total_value).toBe(expectedValue);
      expect(rows[0].holdings_count).toBe(3);
    });
  });

  describe('Transaction Recording', () => {
    let testPortfolioId;

    beforeEach(async () => {
      if (!connection) return;

      const [result] = await connection.execute(
        'INSERT INTO test_portfolios (user_id, name, created_at) VALUES (?, ?, ?)',
        [`test_user_${Date.now()}`, 'Test Portfolio', new Date()]
      );
      testPortfolioId = result.insertId;
    });

    it('records buy transaction', async () => {
      if (!connection || !testPortfolioId) return;

      const transactionData = {
        portfolio_id: testPortfolioId,
        type: 'BUY',
        symbol: 'AAPL',
        quantity: 100,
        price: 150.00,
        fees: 1.00,
        timestamp: new Date()
      };

      const [result] = await connection.execute(
        'INSERT INTO test_transactions (portfolio_id, type, symbol, quantity, price, fees, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)',
        [transactionData.portfolio_id, transactionData.type, transactionData.symbol, transactionData.quantity, transactionData.price, transactionData.fees, transactionData.timestamp]
      );

      expect(result.insertId).toBeGreaterThan(0);
      expect(result.affectedRows).toBe(1);
    });

    it('retrieves transaction history with pagination', async () => {
      if (!connection || !testPortfolioId) return;

      // Insert multiple transactions
      const transactions = [
        { type: 'BUY', symbol: 'AAPL', quantity: 100, price: 150.00 },
        { type: 'BUY', symbol: 'GOOGL', quantity: 50, price: 2500.00 },
        { type: 'SELL', symbol: 'AAPL', quantity: 50, price: 155.00 }
      ];

      for (const tx of transactions) {
        await connection.execute(
          'INSERT INTO test_transactions (portfolio_id, type, symbol, quantity, price, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
          [testPortfolioId, tx.type, tx.symbol, tx.quantity, tx.price, new Date()]
        );
      }

      // Retrieve with pagination
      const [rows] = await connection.execute(`
        SELECT * FROM test_transactions 
        WHERE portfolio_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 2
      `, [testPortfolioId]);

      expect(rows).toHaveLength(2);
      expect(rows[0].symbol).toBe('AAPL'); // Most recent should be SELL
      expect(rows[0].type).toBe('SELL');
    });
  });

  describe('Database Performance and Optimization', () => {
    it('tests query performance with indexes', async () => {
      if (!connection) return;

      // Test that portfolio lookup by user_id is fast
      const startTime = Date.now();
      await connection.execute(
        'SELECT * FROM test_portfolios WHERE user_id = ?',
        ['test_performance_user']
      );
      const queryTime = Date.now() - startTime;

      expect(queryTime).toBeLessThan(100); // Should be very fast with index
    });

    it('tests connection pooling under load', async () => {
      if (!connection) return;

      // Simulate multiple concurrent operations
      const operations = [];
      for (let i = 0; i < 10; i++) {
        operations.push(
          connection.execute('SELECT SLEEP(0.1), ? as operation_id', [i])
        );
      }

      const startTime = Date.now();
      await Promise.all(operations);
      const totalTime = Date.now() - startTime;

      // Should handle concurrent operations efficiently
      expect(totalTime).toBeLessThan(2000); // All operations in under 2 seconds
    });
  });

  describe('AWS RDS Infrastructure Validation', () => {
    it('validates RDS instance configuration', async () => {
      if (!rdsClient || !RDS_INSTANCE_ID) return;

      const command = new DescribeDBInstancesCommand({
        DBInstanceIdentifier: RDS_INSTANCE_ID
      });

      const response = await rdsClient.send(command);
      const dbInstance = response.DBInstances[0];

      expect(dbInstance.DBInstanceStatus).toBe('available');
      expect(dbInstance.Engine).toBe('mysql');
      expect(dbInstance.MultiAZ).toBeDefined();
      expect(dbInstance.VpcSecurityGroups).toBeDefined();
      
      console.log(`✅ RDS Instance Status: ${dbInstance.DBInstanceStatus}`);
      console.log(`✅ Engine: ${dbInstance.Engine} ${dbInstance.EngineVersion}`);
    });

    it('verifies RDS endpoint accessibility', async () => {
      if (!connection) return;

      const [rows] = await connection.execute('SELECT @@hostname as hostname, @@version as version');
      
      expect(rows[0].hostname).toBeDefined();
      expect(rows[0].version).toContain('MySQL');
      
      console.log(`✅ Connected to: ${rows[0].hostname}`);
      console.log(`✅ MySQL Version: ${rows[0].version}`);
    });

    it('tests SSL connection if configured', async () => {
      if (!connection || !DB_CONFIG.ssl) return;

      const [rows] = await connection.execute('SHOW STATUS LIKE "Ssl_cipher"');
      
      if (DB_CONFIG.ssl) {
        expect(rows[0].Value).toBeTruthy(); // Should have SSL cipher
        console.log(`✅ SSL Cipher: ${rows[0].Value}`);
      }
    });
  });
});

// Helper function to set up test tables
async function setupTestTables(connection) {
  const createTables = [
    `CREATE TABLE IF NOT EXISTS test_portfolios (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      risk_level ENUM('conservative', 'moderate', 'aggressive') DEFAULT 'moderate',
      target_allocation JSON,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_user_id (user_id),
      INDEX idx_created_at (created_at)
    )`,
    
    `CREATE TABLE IF NOT EXISTS test_holdings (
      id INT AUTO_INCREMENT PRIMARY KEY,
      portfolio_id INT NOT NULL,
      symbol VARCHAR(10) NOT NULL,
      quantity DECIMAL(10,2) NOT NULL,
      avg_cost_basis DECIMAL(10,2),
      current_price DECIMAL(10,2),
      sector VARCHAR(100),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (portfolio_id) REFERENCES test_portfolios(id) ON DELETE CASCADE,
      INDEX idx_portfolio_id (portfolio_id),
      INDEX idx_symbol (symbol)
    )`,
    
    `CREATE TABLE IF NOT EXISTS test_transactions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      portfolio_id INT NOT NULL,
      type ENUM('BUY', 'SELL', 'DIVIDEND') NOT NULL,
      symbol VARCHAR(10) NOT NULL,
      quantity DECIMAL(10,2) NOT NULL,
      price DECIMAL(10,2) NOT NULL,
      fees DECIMAL(10,2) DEFAULT 0,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (portfolio_id) REFERENCES test_portfolios(id) ON DELETE CASCADE,
      INDEX idx_portfolio_id (portfolio_id),
      INDEX idx_timestamp (timestamp),
      INDEX idx_symbol (symbol)
    )`
  ];

  for (const sql of createTables) {
    await connection.execute(sql);
  }
}

// Helper function to clean up test tables
async function cleanupTestTables(connection) {
  const dropTables = [
    'DROP TABLE IF EXISTS test_transactions',
    'DROP TABLE IF EXISTS test_holdings', 
    'DROP TABLE IF EXISTS test_portfolios'
  ];

  for (const sql of dropTables) {
    try {
      await connection.execute(sql);
    } catch (error) {
      console.warn(`Warning cleaning up table: ${error.message}`);
    }
  }
}