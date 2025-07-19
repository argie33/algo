/**
 * Test Database Setup
 * Configures test environment for integration tests with database mocking or test database
 */

const { DatabaseTestUtils } = require('../utils/database-test-utils');

// Mock database configuration for tests
const mockDatabaseConfig = {
  host: process.env.TEST_DB_HOST || 'localhost',
  port: process.env.TEST_DB_PORT || 5432,
  database: process.env.TEST_DB_NAME || 'test_financial_db',
  user: process.env.TEST_DB_USER || 'test_user',
  password: process.env.TEST_DB_PASSWORD || 'test_pass',
  ssl: false,
  max: 5, // Reduced pool size for tests
  idleTimeoutMillis: 1000,
  connectionTimeoutMillis: 5000
};

// Global database utilities instance
let dbUtils;

// Check if we should use real database or mocks
const USE_REAL_DATABASE = process.env.USE_REAL_DATABASE === 'true';

/**
 * Setup test database environment
 */
async function setupTestDatabase() {
  try {
    if (USE_REAL_DATABASE) {
      // Try to connect to real test database
      dbUtils = new DatabaseTestUtils();
      await dbUtils.initialize(mockDatabaseConfig);
      console.log('✅ Test database connection established');
      return dbUtils;
    } else {
      // Use mock database for tests
      console.log('🔧 Using mock database for tests (set USE_REAL_DATABASE=true for real DB)');
      return setupMockDatabase();
    }
  } catch (error) {
    console.log('⚠️ Real database unavailable, falling back to mocks:', error.message);
    return setupMockDatabase();
  }
}

/**
 * Setup mock database for tests when real database is unavailable
 */
function setupMockDatabase() {
  const mockDb = {
    query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
    createTestUser: jest.fn().mockResolvedValue({
      user_id: 'test-user-' + Date.now(),
      email: 'test@example.com'
    }),
    createTestApiKeys: jest.fn().mockResolvedValue(true),
    cleanupTestUser: jest.fn().mockResolvedValue(true),
    withDatabaseTransaction: jest.fn().mockImplementation(async (callback) => {
      // Mock transaction that calls the callback with a mock client
      const mockClient = {
        query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
        release: jest.fn()
      };
      return await callback(mockClient);
    }),
    cleanup: jest.fn().mockResolvedValue(true)
  };

  return mockDb;
}

/**
 * Cleanup test database
 */
async function cleanupTestDatabase() {
  if (dbUtils && dbUtils.cleanup) {
    await dbUtils.cleanup();
  }
}

/**
 * Get database utilities for tests
 */
function getTestDatabase() {
  return dbUtils;
}

module.exports = {
  setupTestDatabase,
  cleanupTestDatabase,
  getTestDatabase,
  mockDatabaseConfig,
  USE_REAL_DATABASE
};