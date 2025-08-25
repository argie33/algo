/**
 * Simplified Test Database for Backend Testing
 * Works around pg-mem limitations with complex SQL schemas
 * Provides basic database operations for testing without full schema complexity
 */

const { newDb } = require('pg-mem');

class SimplifiedTestDatabase {
  constructor() {
    this.db = null;
    this.client = null;
    this.isInitialized = false;
  }

  async initialize() {
    try {
      console.log('🔧 Initializing simplified test database...');
      
      // Create pg-mem database
      this.db = newDb();
      
      // Create simplified tables that work with pg-mem limitations
      await this.createSimplifiedTables();
      
      // Get the PostgreSQL adapter and create a client (pg-mem pattern)
      const adapter = this.db.adapters.createPg();
      this.client = new adapter.Client();
      this.isInitialized = true;
      
      console.log('✅ Simplified test database ready');
      return this.client;
    } catch (error) {
      console.error('❌ Failed to initialize simplified test database:', error.message);
      throw error;
    }
  }

  async createSimplifiedTables() {
    // Create simple tables without DECIMAL, TIMESTAMP WITH TIME ZONE, DEFAULT NOW()
    // These tables are for testing basic CRUD operations, not full schema validation
    
    await this.db.public.none(`
      CREATE TABLE IF NOT EXISTS test_users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255),
        created_at VARCHAR(30)
      );
    `);

    await this.db.public.none(`
      CREATE TABLE IF NOT EXISTS test_stocks (
        symbol VARCHAR(10) PRIMARY KEY,
        price FLOAT,
        volume INTEGER
      );
    `);

    await this.db.public.none(`
      CREATE TABLE IF NOT EXISTS test_watchlist (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        symbol VARCHAR(10),
        created_at VARCHAR(30)
      );
    `);

    await this.db.public.none(`
      CREATE TABLE IF NOT EXISTS test_api_keys (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255),
        provider VARCHAR(50),
        encrypted_data TEXT
      );
    `);

    console.log('✅ Simplified test tables created');
  }

  async query(sql, params = []) {
    if (!this.isInitialized) {
      throw new Error('Database not initialized. Call initialize() first.');
    }

    try {
      return await this.client.query(sql, params);
    } catch (error) {
      console.error('Query failed:', error.message);
      throw error;
    }
  }

  // Helper methods for common test operations
  async insertTestUser(email) {
    const result = await this.query(
      'INSERT INTO test_users (email, created_at) VALUES ($1, $2) RETURNING *',
      [email, new Date().toISOString()]
    );
    return result.rows[0];
  }

  async insertTestStock(symbol, price, volume) {
    const result = await this.query(
      'INSERT INTO test_stocks (symbol, price, volume) VALUES ($1, $2, $3) RETURNING *',
      [symbol, price, volume]
    );
    return result.rows[0];
  }

  async insertTestWatchlistItem(userId, symbol) {
    const result = await this.query(
      'INSERT INTO test_watchlist (user_id, symbol, created_at) VALUES ($1, $2, $3) RETURNING *',
      [userId, symbol, new Date().toISOString()]
    );
    return result.rows[0];
  }

  async insertTestApiKey(userId, provider, encryptedData) {
    const result = await this.query(
      'INSERT INTO test_api_keys (user_id, provider, encrypted_data) VALUES ($1, $2, $3) RETURNING *',
      [userId, provider, encryptedData]
    );
    return result.rows[0];
  }

  async cleanup() {
    try {
      if (this.client) {
        // Clear all test data
        await this.client.query('DELETE FROM test_watchlist');
        await this.client.query('DELETE FROM test_api_keys');
        await this.client.query('DELETE FROM test_stocks');
        await this.client.query('DELETE FROM test_users');
        
        await this.client.end();
        console.log('✅ Simplified test database cleaned up');
      }
    } catch (error) {
      console.error('❌ Cleanup failed:', error.message);
    }
  }

  // Mock database health check for testing
  async healthCheck() {
    if (!this.isInitialized) {
      return { healthy: false, error: 'Database not initialized' };
    }

    try {
      await this.query('SELECT 1 as test');
      return { healthy: true, timestamp: new Date().toISOString() };
    } catch (error) {
      return { healthy: false, error: error.message };
    }
  }
}

module.exports = {
  SimplifiedTestDatabase,
  createSimplifiedTestDatabase: () => new SimplifiedTestDatabase()
};