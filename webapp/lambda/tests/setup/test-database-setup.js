/**
 * Test Database Setup - REAL DATABASE ONLY
 * Configures test environment for integration tests with real database connections
 */

const { DatabaseTestUtils } = require('../utils/database-test-utils');

// Configure test environment for authentication
if (!process.env.NODE_ENV) {
  process.env.NODE_ENV = 'test';
}
process.env.ALLOW_DEV_AUTH_BYPASS = 'true';

console.log('🔧 Test environment configured for auth bypass:', {
  NODE_ENV: process.env.NODE_ENV,
  ALLOW_DEV_AUTH_BYPASS: process.env.ALLOW_DEV_AUTH_BYPASS
});

// Real database configuration for tests
const realDatabaseConfig = {
  host: process.env.TEST_DB_HOST || process.env.DB_ENDPOINT || 'localhost',
  port: process.env.TEST_DB_PORT || 5432,
  database: process.env.TEST_DB_NAME || 'financial_db',
  user: process.env.TEST_DB_USER || 'postgres',
  password: process.env.TEST_DB_PASSWORD || process.env.DB_PASSWORD,
  ssl: false,
  max: 5, // Reduced pool size for tests
  idleTimeoutMillis: 1000,
  connectionTimeoutMillis: 5000
};

// Global database utilities instance
let dbUtils;

/**
 * Setup test database environment - REAL DATABASE ONLY
 */
async function setupTestDatabase() {
  try {
    // Always try to connect to real database
    dbUtils = new DatabaseTestUtils();
    await dbUtils.initialize(); // No config parameter needed - uses environment variables
    console.log('✅ Real test database connection established');
    return dbUtils;
  } catch (error) {
    console.error('❌ Real database connection failed:', error.message);
    console.error('❌ Tests require real database connection - no fallbacks');
    throw new Error('Real database required for integration tests');
  }
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
  realDatabaseConfig
};