/**
 * Database Test Utilities
 * Provides transaction management and cleanup for integration tests
 */

const { getPool } = require('../../utils/database');

class DatabaseTestUtils {
  constructor() {
    this.pool = null;
    this.activeConnections = new Set();
    this.rollbackFunctions = [];
  }

  async initialize() {
    try {
      this.pool = await getPool();
      console.log('✅ Database test utilities initialized');
    } catch (error) {
      console.error('❌ Failed to initialize database test utilities:', error);
      throw error;
    }
  }

  /**
   * Start a test transaction that will be automatically rolled back
   */
  async startTestTransaction() {
    if (!this.pool) {
      await this.initialize();
    }

    const client = await this.pool.connect();
    this.activeConnections.add(client);

    await client.query('BEGIN');
    
    // Create rollback function
    const rollback = async () => {
      try {
        await client.query('ROLLBACK');
        client.release();
        this.activeConnections.delete(client);
      } catch (error) {
        console.error('Error during transaction rollback:', error);
      }
    };

    this.rollbackFunctions.push(rollback);
    return client;
  }

  /**
   * Insert test data that will be cleaned up automatically
   */
  async insertTestData(tableName, data, client) {
    if (!client) {
      client = await this.startTestTransaction();
    }

    const columns = Object.keys(data);
    const values = Object.values(data);
    const placeholders = values.map((_, index) => `$${index + 1}`).join(', ');

    const query = `
      INSERT INTO ${tableName} (${columns.join(', ')})
      VALUES (${placeholders})
      RETURNING *
    `;

    const result = await client.query(query, values);
    return result.rows[0];
  }

  /**
   * Create test user with cleanup
   */
  async createTestUser(userData = {}) {
    const defaultUser = {
      user_id: `test-user-${Date.now()}`,
      email: `test-${Date.now()}@example.com`,
      username: `testuser${Date.now()}`,
      created_at: new Date(),
      updated_at: new Date()
    };

    const user = { ...defaultUser, ...userData };
    const client = await this.startTestTransaction();
    return await this.insertTestData('users', user, client);
  }

  /**
   * Create test API keys for a user
   */
  async createTestApiKeys(userId, apiKeys = {}) {
    const defaultKeys = {
      user_id: userId,
      alpaca_api_key: 'test-alpaca-key',
      alpaca_secret_key: 'test-alpaca-secret',
      polygon_api_key: 'test-polygon-key',
      finnhub_api_key: 'test-finnhub-key',
      created_at: new Date(),
      updated_at: new Date()
    };

    const keys = { ...defaultKeys, ...apiKeys };
    const client = await this.startTestTransaction();
    return await this.insertTestData('api_keys', keys, client);
  }

  /**
   * Create test portfolio positions
   */
  async createTestPortfolio(userId, positions = []) {
    if (positions.length === 0) {
      positions = [
        {
          user_id: userId,
          symbol: 'AAPL',
          quantity: 100,
          avg_cost: 150.00,
          current_price: 155.00,
          created_at: new Date(),
          updated_at: new Date()
        },
        {
          user_id: userId,
          symbol: 'MSFT',
          quantity: 50,
          avg_cost: 300.00,
          current_price: 310.00,
          created_at: new Date(),
          updated_at: new Date()
        }
      ];
    }

    const client = await this.startTestTransaction();
    const insertedPositions = [];

    for (const position of positions) {
      const inserted = await this.insertTestData('portfolio', position, client);
      insertedPositions.push(inserted);
    }

    return insertedPositions;
  }

  /**
   * Create test price data
   */
  async createTestPriceData(symbol, days = 5) {
    const client = await this.startTestTransaction();
    const priceData = [];

    for (let i = days; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);

      const basePrice = 100 + Math.random() * 50;
      const data = {
        symbol: symbol,
        date: date.toISOString().split('T')[0],
        open: basePrice + Math.random() * 5 - 2.5,
        high: basePrice + Math.random() * 8,
        low: basePrice - Math.random() * 8,
        close: basePrice + Math.random() * 5 - 2.5,
        volume: Math.floor(Math.random() * 1000000) + 100000,
        adj_close: basePrice + Math.random() * 5 - 2.5
      };

      const inserted = await this.insertTestData('price_daily', data, client);
      priceData.push(inserted);
    }

    return priceData;
  }

  /**
   * Execute raw SQL query in test transaction
   */
  async executeQuery(query, params = [], client) {
    if (!client) {
      client = await this.startTestTransaction();
    }

    return await client.query(query, params);
  }

  /**
   * Cleanup all test data and close connections
   */
  async cleanup() {
    console.log(`🧹 Cleaning up ${this.rollbackFunctions.length} test transactions...`);

    // Rollback all transactions
    await Promise.all(this.rollbackFunctions.map(rollback => rollback()));
    this.rollbackFunctions = [];

    // Close any remaining connections
    for (const client of this.activeConnections) {
      try {
        client.release();
      } catch (error) {
        console.error('Error releasing connection:', error);
      }
    }
    this.activeConnections.clear();

    console.log('✅ Database test cleanup completed');
  }

  /**
   * Wait for database operations to complete
   */
  async waitForDatabase(timeout = 5000) {
    const start = Date.now();
    while (this.activeConnections.size > 0 && (Date.now() - start) < timeout) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    if (this.activeConnections.size > 0) {
      console.warn(`⚠️ ${this.activeConnections.size} database connections still active after ${timeout}ms`);
    }
  }

  /**
   * Verify table exists and has expected structure
   */
  async verifyTableStructure(tableName, expectedColumns = []) {
    const client = await this.startTestTransaction();
    
    const result = await client.query(`
      SELECT column_name, data_type, is_nullable
      FROM information_schema.columns
      WHERE table_name = $1
      ORDER BY ordinal_position
    `, [tableName]);

    const actualColumns = result.rows.map(row => ({
      name: row.column_name,
      type: row.data_type,
      nullable: row.is_nullable === 'YES'
    }));

    return {
      exists: result.rows.length > 0,
      columns: actualColumns,
      hasExpectedColumns: expectedColumns.length === 0 || 
        expectedColumns.every(col => 
          actualColumns.some(actual => actual.name === col)
        )
    };
  }
}

// Export singleton instance
const dbTestUtils = new DatabaseTestUtils();

module.exports = {
  DatabaseTestUtils,
  dbTestUtils
};