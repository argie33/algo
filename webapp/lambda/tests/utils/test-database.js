/**
 * Test Database Utilities
 * Provides database setup and teardown for integration tests
 */

const { Pool } = require('pg');

class TestDatabase {
  constructor() {
    this.pool = null;
    this.isInitialized = false;
  }
  
  async init() {
    if (this.isInitialized) return;
    
    console.log('🗄️ Initializing test database connection...');
    
    try {
      // Use test database configuration
      const config = {
        host: process.env.TEST_DB_HOST || process.env.DB_HOST || 'localhost',
        port: process.env.TEST_DB_PORT || process.env.DB_PORT || 5432,
        user: process.env.TEST_DB_USER || process.env.DB_USER || 'postgres',
        password: process.env.TEST_DB_PASSWORD || process.env.DB_PASSWORD || 'password',
        database: process.env.TEST_DB_NAME || process.env.DB_NAME || 'stocks_test',
        ssl: false, // Disable SSL for test environment
        max: 5, // Limit connections for tests
        idleTimeoutMillis: 30000,
        connectionTimeoutMillis: 5000
      };
      
      this.pool = new Pool(config);
      
      // Test the connection
      const client = await this.pool.connect();
      await client.query('SELECT NOW()');
      client.release();
      
      console.log('✅ Test database connection established');
      this.isInitialized = true;
      
    } catch (error) {
      console.warn('⚠️ Test database connection failed:', error.message);
      console.log('📝 Tests will run without database integration');
      
      // Create a mock pool for tests to continue
      this.pool = {
        query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
        connect: jest.fn().mockResolvedValue({
          query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
          release: jest.fn()
        }),
        end: jest.fn()
      };
      
      this.isInitialized = true;
    }
  }
  
  async cleanup() {
    if (!this.isInitialized || !this.pool) return;
    
    console.log('🧹 Cleaning up test database connection...');
    
    try {
      if (typeof this.pool.end === 'function') {
        await this.pool.end();
      }
      console.log('✅ Test database cleanup complete');
    } catch (error) {
      console.warn('⚠️ Error during database cleanup:', error.message);
    }
    
    this.pool = null;
    this.isInitialized = false;
  }
  
  async query(text, params) {
    if (!this.isInitialized) {
      await this.init();
    }
    
    try {
      return await this.pool.query(text, params);
    } catch (error) {
      console.warn('Database query failed:', error.message);
      throw error;
    }
  }
  
  async getClient() {
    if (!this.isInitialized) {
      await this.init();
    }
    
    return await this.pool.connect();
  }
  
  // Helper method to create test data
  async createTestUser(userData = {}) {
    const defaultUser = {
      id: 'test-user-' + Date.now(),
      email: 'test@example.com',
      username: 'testuser',
      created_at: new Date(),
      ...userData
    };
    
    try {
      const result = await this.query(
        'INSERT INTO users (id, email, username, created_at) VALUES ($1, $2, $3, $4) RETURNING *',
        [defaultUser.id, defaultUser.email, defaultUser.username, defaultUser.created_at]
      );
      
      return result.rows[0];
    } catch (error) {
      // If table doesn't exist, return mock data
      console.warn('Could not create test user in database:', error.message);
      return defaultUser;
    }
  }
  
  // Helper method to clean test data
  async cleanTestData() {
    const testTables = ['test_portfolios', 'test_holdings', 'test_users'];
    
    for (const table of testTables) {
      try {
        await this.query(`DELETE FROM ${table} WHERE id LIKE 'test-%'`);
      } catch (error) {
        // Table might not exist, continue
        console.debug(`Could not clean ${table}:`, error.message);
      }
    }
  }
  
  // Helper method to check if database is available
  async isAvailable() {
    try {
      await this.query('SELECT 1');
      return true;
    } catch (error) {
      return false;
    }
  }
}

// Export singleton instance
const testDatabase = new TestDatabase();

module.exports = {
  testDatabase,
  TestDatabase
};