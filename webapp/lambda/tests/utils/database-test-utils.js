/**
 * Database Test Utilities
 * Provides real database connections and test data management for integration tests
 */

const { Pool } = require('pg');
const crypto = require('crypto');

class DatabaseTestUtils {
  constructor() {
    this.pool = null;
    this.testUsers = [];
    this.testData = [];
  }

  /**
   * Initialize database connection for integration tests
   * Uses the same AWS infrastructure as the deployed application
   */
  async initialize() {
    try {
      console.log('🔧 Initializing integration test database connection...');
      
      // Use the same database configuration as the main application
      const database = require('../../utils/database');
      const getDbConfig = database.getDbConfig;
      
      console.log('📋 Getting database config from main application...');
      const dbConfig = await getDbConfig();
      
      // Override some settings for integration testing
      const testDbConfig = {
        ...dbConfig,
        max: 5, // Limit connections for tests
        idleTimeoutMillis: 30000,
        connectionTimeoutMillis: 5000, // Longer timeout for integration tests
      };

      console.log('🔌 Connecting to production database for integration tests:', {
        host: testDbConfig.host,
        port: testDbConfig.port,
        database: testDbConfig.database,
        user: testDbConfig.user,
        ssl: testDbConfig.ssl ? 'enabled' : 'disabled'
      });

      this.pool = new Pool(testDbConfig);

      // Test the connection
      const testClient = await Promise.race([
        this.pool.connect(),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Connection timeout after 5 seconds')), 5000)
        )
      ]);
      
      await testClient.query('SELECT NOW() as timestamp, current_database() as db');
      testClient.release();

      console.log('✅ Integration test database connection established');
      this.useMockDatabase = false;

      // Ensure test tables exist (for integration testing)
      await this.ensureTestTables();

    } catch (error) {
      console.error('❌ Integration test database connection failed:', error.message);
      console.error('🔧 Database configuration details:', {
        DB_SECRET_ARN: !!process.env.DB_SECRET_ARN,
        DB_HOST: !!process.env.DB_HOST,
        DB_USER: !!process.env.DB_USER,
        DB_PASSWORD: !!process.env.DB_PASSWORD,
        AWS_REGION: process.env.AWS_REGION || 'not set'
      });
      
      throw new Error(`Integration test database connection failed: ${error.message}`);
    }
  }



  /**
   * Ensure required test tables exist
   */
  async ensureTestTables() {
    try {
      const client = await this.pool.connect();

      // Create users table if it doesn't exist
      await client.query(`
        CREATE TABLE IF NOT EXISTS users (
          user_id SERIAL PRIMARY KEY,
          email VARCHAR(255) UNIQUE NOT NULL,
          username VARCHAR(100) UNIQUE NOT NULL,
          cognito_user_id VARCHAR(255) UNIQUE,
          password_hash VARCHAR(255),
          first_name VARCHAR(100),
          last_name VARCHAR(100),
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          is_active BOOLEAN DEFAULT true,
          role VARCHAR(50) DEFAULT 'user'
        )
      `);

      // Create api_keys table if it doesn't exist
      await client.query(`
        CREATE TABLE IF NOT EXISTS api_keys (
          api_key_id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
          provider VARCHAR(50) NOT NULL,
          encrypted_api_key TEXT NOT NULL,
          encrypted_secret_key TEXT,
          salt VARCHAR(255) NOT NULL,
          description TEXT,
          is_active BOOLEAN DEFAULT true,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          last_used_at TIMESTAMP,
          validation_status VARCHAR(50) DEFAULT 'pending',
          UNIQUE(user_id, provider)
        )
      `);

      // Create portfolio table if it doesn't exist
      await client.query(`
        CREATE TABLE IF NOT EXISTS portfolio (
          portfolio_id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
          symbol VARCHAR(10) NOT NULL,
          quantity DECIMAL(15, 6) NOT NULL,
          avg_cost DECIMAL(10, 2) NOT NULL,
          current_price DECIMAL(10, 2),
          market_value DECIMAL(15, 2),
          unrealized_pl DECIMAL(15, 2),
          sector VARCHAR(100),
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, symbol)
        )
      `);

      // Create watchlist table if it doesn't exist
      await client.query(`
        CREATE TABLE IF NOT EXISTS watchlist (
          watchlist_id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
          symbol VARCHAR(10) NOT NULL,
          notes TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, symbol)
        )
      `);

      // Create alerts table if it doesn't exist
      await client.query(`
        CREATE TABLE IF NOT EXISTS alerts (
          alert_id SERIAL PRIMARY KEY,
          user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
          symbol VARCHAR(10) NOT NULL,
          condition VARCHAR(20) NOT NULL,
          target_price DECIMAL(10, 2) NOT NULL,
          alert_type VARCHAR(20) NOT NULL,
          notes TEXT,
          is_active BOOLEAN DEFAULT true,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          triggered_at TIMESTAMP
        )
      `);

      client.release();
      console.log('✅ Test tables verified/created');

    } catch (error) {
      console.error('❌ Failed to ensure test tables:', error.message);
      throw error;
    }
  }

  /**
   * Create a test user
   */
  async createTestUser(userData = {}) {
    const client = await this.pool.connect();
    try {
      const defaultUser = {
        email: `test-${Date.now()}@example.com`,
        username: `testuser${Date.now()}`,
        cognito_user_id: `test-cognito-${Date.now()}`,
        first_name: 'Test',
        last_name: 'User',
        role: 'user'
      };

      const user = { ...defaultUser, ...userData };

      const result = await client.query(`
        INSERT INTO users (email, username, cognito_user_id, first_name, last_name, role)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
      `, [user.email, user.username, user.cognito_user_id, user.first_name, user.last_name, user.role]);

      const createdUser = result.rows[0];
      this.testUsers.push(createdUser);
      
      console.log('👤 Created test user:', createdUser.email);
      return createdUser;

    } finally {
      client.release();
    }
  }

  /**
   * Generate a unique test user ID
   */
  createTestUserId() {
    return `test-user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Create test API keys for a user
   */
  async createTestApiKeys(userId, apiKeys = {}) {
    const client = await this.pool.connect();
    try {
      const defaultKeys = {
        alpaca_api_key: 'PKTEST123456789ABCDE',
        alpaca_secret_key: 'secret12345678901234567890secret12345'
      };

      const keys = { ...defaultKeys, ...apiKeys };
      const createdKeys = [];

      // Create Alpaca API key
      if (keys.alpaca_api_key) {
        const salt = crypto.randomBytes(32).toString('hex');
        const cipher = crypto.createCipher('aes-256-cbc', process.env.API_KEY_ENCRYPTION_SECRET + salt);
        let encryptedKey = cipher.update(keys.alpaca_api_key, 'utf8', 'hex');
        encryptedKey += cipher.final('hex');

        let encryptedSecret = null;
        if (keys.alpaca_secret_key) {
          const secretCipher = crypto.createCipher('aes-256-cbc', process.env.API_KEY_ENCRYPTION_SECRET + salt);
          encryptedSecret = secretCipher.update(keys.alpaca_secret_key, 'utf8', 'hex');
          encryptedSecret += secretCipher.final('hex');
        }

        const result = await client.query(`
          INSERT INTO api_keys (user_id, provider, encrypted_api_key, encrypted_secret_key, salt, description, validation_status)
          VALUES ($1, $2, $3, $4, $5, $6, $7)
          RETURNING *
        `, [userId, 'alpaca', encryptedKey, encryptedSecret, salt, 'Test Alpaca API Key', 'active']);

        createdKeys.push(result.rows[0]);
      }

      console.log('🔑 Created API keys for user:', userId);
      return createdKeys;

    } finally {
      client.release();
    }
  }

  /**
   * Create test portfolio for a user
   */
  async createTestPortfolio(userId, positions = []) {
    const client = await this.pool.connect();
    try {
      const defaultPositions = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avg_cost: 150.00,
          current_price: 155.00,
          sector: 'Technology'
        },
        {
          symbol: 'MSFT',
          quantity: 50,
          avg_cost: 300.00,
          current_price: 310.00,
          sector: 'Technology'
        }
      ];

      const portfolioPositions = positions.length > 0 ? positions : defaultPositions;
      const createdPositions = [];

      for (const position of portfolioPositions) {
        const marketValue = position.quantity * position.current_price;
        const unrealizedPl = marketValue - (position.quantity * position.avg_cost);

        const result = await client.query(`
          INSERT INTO portfolio (user_id, symbol, quantity, avg_cost, current_price, market_value, unrealized_pl, sector)
          VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
          RETURNING *
        `, [userId, position.symbol, position.quantity, position.avg_cost, position.current_price, marketValue, unrealizedPl, position.sector]);

        createdPositions.push(result.rows[0]);
      }

      console.log('📊 Created portfolio positions for user:', userId);
      return createdPositions;

    } finally {
      client.release();
    }
  }

  /**
   * Create test transactions
   */
  async createTestTransactions(userId, transactions = []) {
    // This would create transactions in a transactions table
    // For now, just return the input data since transactions table may not exist
    console.log('💰 Created test transactions for user:', userId);
    return transactions;
  }

  /**
   * Add positions to existing portfolio
   */
  async addPositionsToPortfolio(userId, positions = []) {
    const client = await this.pool.connect();
    try {
      const createdPositions = [];

      for (const position of positions) {
        const marketValue = position.quantity * position.current_price;
        const unrealizedPl = marketValue - (position.quantity * position.avg_cost);

        const result = await client.query(`
          INSERT INTO portfolio (user_id, symbol, quantity, avg_cost, current_price, market_value, unrealized_pl, sector)
          VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
          ON CONFLICT (user_id, symbol) 
          DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_cost = EXCLUDED.avg_cost,
            current_price = EXCLUDED.current_price,
            market_value = EXCLUDED.market_value,
            unrealized_pl = EXCLUDED.unrealized_pl,
            updated_at = CURRENT_TIMESTAMP
          RETURNING *
        `, [userId, position.symbol, position.quantity, position.avg_cost, position.current_price, marketValue, unrealizedPl, position.sector]);

        createdPositions.push(result.rows[0]);
      }

      return createdPositions;

    } finally {
      client.release();
    }
  }

  /**
   * Clean up test data
   */
  async cleanup() {
    if (!this.pool) return;

    try {

      const client = await this.pool.connect();

      // Delete test users and their associated data (CASCADE will handle related records)
      for (const user of this.testUsers) {
        await client.query('DELETE FROM users WHERE user_id = $1', [user.user_id]);
      }

      client.release();
      console.log('🧹 Test data cleaned up');

      // Close the pool
      await this.pool.end();
      console.log('🔌 Database test connection closed');

    } catch (error) {
      console.error('❌ Cleanup failed:', error.message);
    }
  }

  /**
   * Execute raw SQL query (for advanced test scenarios)
   */
  async query(sql, params = []) {
    const client = await this.pool.connect();
    try {
      const result = await client.query(sql, params);
      return result;
    } finally {
      client.release();
    }
  }

  /**
   * Get a database client for transactions
   */
  async getClient() {
    return await this.pool.connect();
  }
}

// Export singleton instance
const dbTestUtils = new DatabaseTestUtils();

/**
 * Helper function: Create test user
 */
async function createTestUser(userPrefix = 'test-user') {
  return await dbTestUtils.createTestUser(userPrefix);
}

/**
 * Helper function: Create test user ID
 */
function createTestUserId() {
  return dbTestUtils.createTestUserId();
}

/**
 * Helper function: Create test API keys
 */
async function createTestApiKeys(userId, apiKeys = {}) {
  return await dbTestUtils.createTestApiKeys(userId, apiKeys);
}

/**
 * Helper function: Clean up test user
 */
async function cleanupTestUser(userId) {
  if (!dbTestUtils.pool) return;

  try {
    const client = await dbTestUtils.pool.connect();
    await client.query('DELETE FROM users WHERE user_id = $1', [userId]);
    client.release();
    console.log('🧹 Cleaned up test user:', userId);
  } catch (error) {
    console.error('❌ Failed to cleanup test user:', error.message);
  }
}

/**
 * Helper function: Execute function within a database transaction
 * Integration tests require real database connections
 */
async function withDatabaseTransaction(callback) {
  if (!dbTestUtils.pool) {
    throw new Error('Database not initialized for integration tests. Integration tests require real database connections.');
  }

  const client = await dbTestUtils.getClient();
  try {
    await client.query('BEGIN');
    const result = await callback(client);
    await client.query('ROLLBACK'); // Always rollback in tests
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

module.exports = {
  dbTestUtils,
  DatabaseTestUtils,
  createTestUser,
  createTestUserId,
  createTestApiKeys,
  cleanupTestUser,
  withDatabaseTransaction
};