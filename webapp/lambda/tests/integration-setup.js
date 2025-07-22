/**
 * Integration Test Setup - Runs before each test file
 * Configures real database connections and services
 */

const { Pool } = require('pg');

// Global test database connection
global.testDbPool = null;
global.testUserId = 1; // Use real test user ID
global.testUserEmail = 'test@example.com';

// Setup real database connection for each test file
beforeAll(async () => {
  console.log('🔌 Setting up real database connection for tests...');
  
  if (global.__DB_CONFIG__) {
    global.testDbPool = new Pool(global.__DB_CONFIG__);
    
    // Test connection
    try {
      const client = await global.testDbPool.connect();
      await client.query('SELECT 1');
      client.release();
      console.log('✅ Real database connection established');
    } catch (error) {
      console.error('❌ Database connection failed:', error.message);
      throw error;
    }
  } else {
    console.warn('⚠️ No database config available - tests may fail');
  }
});

// Cleanup after each test file
afterAll(async () => {
  console.log('🧹 Cleaning up real database connections...');
  
  if (global.testDbPool) {
    await global.testDbPool.end();
    console.log('✅ Database connections closed');
  }
});

// Real authentication helper for tests
global.createTestAuthToken = () => {
  const jwt = require('jsonwebtoken');
  return jwt.sign(
    { 
      sub: global.testUserId.toString(),
      email: global.testUserEmail,
      exp: Math.floor(Date.now() / 1000) + 3600 
    },
    process.env.JWT_SECRET || 'test-jwt-secret'
  );
};

// Real database query helper
global.queryTestDb = async (sql, params = []) => {
  if (!global.testDbPool) {
    throw new Error('Test database not initialized');
  }
  
  const client = await global.testDbPool.connect();
  try {
    const result = await client.query(sql, params);
    return result;
  } finally {
    client.release();
  }
};

// Real user creation helper
global.createTestUser = async (email = 'test@example.com', userData = {}) => {
  const result = await global.queryTestDb(
    'INSERT INTO users (email, first_name, last_name, is_active, email_verified) VALUES ($1, $2, $3, $4, $5) RETURNING id',
    [
      email,
      userData.firstName || 'Test',
      userData.lastName || 'User',
      userData.isActive !== false,
      userData.emailVerified !== false
    ]
  );
  return result.rows[0].id;
};

// Real portfolio helper
global.createTestPortfolio = async (userId, symbol = 'AAPL', quantity = 100) => {
  const result = await global.queryTestDb(
    'INSERT INTO portfolio (user_id, symbol, quantity, average_cost, current_price, market_value) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id',
    [userId, symbol, quantity, 150.00, 175.50, quantity * 175.50]
  );
  return result.rows[0].id;
};

console.log('🚀 Real integration test setup loaded - NO MOCKS');