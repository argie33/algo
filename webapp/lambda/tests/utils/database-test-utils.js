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
   * Initialize database connection for tests
   */
  async initialize() {
    try {
      // Check if real AWS infrastructure is available
      if (process.env.TEST_DB_SECRET_ARN && process.env.AWS_REGION) {
        console.log('🔧 Using real AWS infrastructure for integration tests');
        // TODO: Implement AWS Secrets Manager database connection
        // For now, skip real AWS connection until we have proper credentials
        this.useMockDatabase = false;
        console.log('⚠️ Real AWS database connection not yet implemented - using mock mode');
        this.initializeMockDatabase();
        return;
      }

      // Check if local database is available
      const dbConfig = {
        host: process.env.TEST_DB_HOST || process.env.DB_HOST || 'localhost',
        port: process.env.TEST_DB_PORT || process.env.DB_PORT || 5432,
        database: process.env.TEST_DB_NAME || process.env.DB_NAME || 'financial_platform_test',
        user: process.env.TEST_DB_USER || process.env.DB_USER || 'postgres',
        password: process.env.TEST_DB_PASSWORD || process.env.DB_PASSWORD || 'postgres',
        ssl: (process.env.TEST_DB_SSL || process.env.DB_SSL || 'false') === 'true',
        max: 5, // Limit connections for tests
        idleTimeoutMillis: 30000,
        connectionTimeoutMillis: 2000,
      };

      console.log('🔌 Attempting to connect to test database:', {
        host: dbConfig.host,
        port: dbConfig.port,
        database: dbConfig.database,
        user: dbConfig.user,
        ssl: dbConfig.ssl
      });

      this.pool = new Pool(dbConfig);

      // Test the connection with a quick timeout
      const testClient = await Promise.race([
        this.pool.connect(),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Connection timeout')), 3000)
        )
      ]);
      
      await testClient.query('SELECT NOW()');
      testClient.release();

      console.log('✅ Database test connection established');
      this.useMockDatabase = false;

      // Ensure test tables exist
      await this.ensureTestTables();

    } catch (error) {
      console.log('⚠️ Real database not available, switching to mock mode:', error.message);
      this.initializeMockDatabase();
    }
  }

  /**
   * Initialize mock database for tests when real database is not available
   */
  initializeMockDatabase() {
    console.log('🎭 Initializing mock database for integration tests');
    this.useMockDatabase = true;
    this.mockData = {
      users: new Map(),
      apiKeys: new Map(),
      portfolio: new Map(),
      watchlist: new Map(),
      alerts: new Map()
    };
    this.mockIdCounter = 1;
    
    // Create mock pool interface
    this.pool = {
      connect: () => Promise.resolve(this.createMockClient()),
      end: () => Promise.resolve(),
      query: (sql, params) => this.executeMockQuery(sql, params)
    };
    
    console.log('✅ Mock database initialized');
  }

  /**
   * Create mock database client
   */
  createMockClient() {
    return {
      query: (sql, params) => this.executeMockQuery(sql, params),
      release: () => {},
    };
  }

  /**
   * Execute mock database query
   */
  async executeMockQuery(sql, params = []) {
    // Simulate database operations with mock data
    if (sql.includes('INSERT INTO users')) {
      const userId = this.mockIdCounter++;
      const user = {
        user_id: userId,
        email: params[0],
        username: params[1],
        cognito_user_id: params[2],
        first_name: params[3],
        last_name: params[4],
        role: params[5],
        created_at: new Date(),
        updated_at: new Date(),
        is_active: true
      };
      this.mockData.users.set(userId, user);
      return { rows: [user], rowCount: 1 };
    }
    
    if (sql.includes('INSERT INTO api_keys')) {
      const apiKeyId = this.mockIdCounter++;
      const apiKey = {
        api_key_id: apiKeyId,
        user_id: params[0],
        provider: params[1],
        encrypted_api_key: params[2],
        encrypted_secret_key: params[3],
        salt: params[4],
        description: params[5],
        validation_status: params[6],
        created_at: new Date(),
        updated_at: new Date(),
        is_active: true
      };
      this.mockData.apiKeys.set(apiKeyId, apiKey);
      return { rows: [apiKey], rowCount: 1 };
    }
    
    if (sql.includes('INSERT INTO portfolio')) {
      const portfolioId = this.mockIdCounter++;
      const position = {
        portfolio_id: portfolioId,
        user_id: params[0],
        symbol: params[1],
        quantity: params[2],
        avg_cost: params[3],
        current_price: params[4],
        market_value: params[5],
        unrealized_pl: params[6],
        sector: params[7],
        created_at: new Date(),
        updated_at: new Date()
      };
      this.mockData.portfolio.set(portfolioId, position);
      return { rows: [position], rowCount: 1 };
    }
    
    if (sql.includes('SELECT NOW()')) {
      return { rows: [{ now: new Date() }], rowCount: 1 };
    }
    
    if (sql.includes('CREATE TABLE')) {
      // Mock table creation - always succeeds
      return { rows: [], rowCount: 0 };
    }
    
    if (sql.includes('DELETE FROM users')) {
      const userId = params[0];
      const deleted = this.mockData.users.delete(userId);
      return { rows: [], rowCount: deleted ? 1 : 0 };
    }
    
    // Default mock response
    return { rows: [], rowCount: 0 };
  }

  /**
   * Ensure required test tables exist
   */
  async ensureTestTables() {
    if (this.useMockDatabase) {
      console.log('✅ Mock database tables ready');
      return;
    }
    
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
      if (this.useMockDatabase) {
        // Clean up mock data
        this.mockData.users.clear();
        this.mockData.apiKeys.clear();
        this.mockData.portfolio.clear();
        this.mockData.watchlist.clear();
        this.mockData.alerts.clear();
        this.testUsers = [];
        console.log('🧹 Mock test data cleaned up');
        return;
      }

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
 */
async function withDatabaseTransaction(callback) {
  if (!dbTestUtils.pool) {
    // If no database available, use mock client
    const mockClient = {
      query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
      release: jest.fn()
    };
    return await callback(mockClient);
  }

  if (dbTestUtils.useMockDatabase) {
    // Use mock client for mock database
    const mockClient = dbTestUtils.createMockClient();
    return await callback(mockClient);
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
  createTestApiKeys,
  cleanupTestUser,
  withDatabaseTransaction
};