/**
 * Jest setup file for tests
 * Simplified setup to prevent hanging
 */

// Configure environment for tests
process.env.NODE_ENV = 'test';
process.env.JWT_SECRET = 'test-secret-key-for-testing-only';
process.env.ALLOW_DEV_BYPASS = 'true'; // Allow dev bypass for tests

// Set database environment variables for PostgreSQL connection
process.env.DB_HOST = 'localhost';
process.env.DB_USER = 'postgres';
process.env.DB_PASSWORD = 'password';
process.env.DB_NAME = 'stocks';
process.env.DB_PORT = '5432';
process.env.DB_SSL = 'false';

// Simplified test setup - no complex database operations
console.log('✅ Test environment configured');

// Optional: Test basic connectivity in individual tests if needed
module.exports = {
  // Export configuration for tests to use
  testConfig: {
    dbHost: process.env.DB_HOST,
    dbName: process.env.DB_NAME,
    jwtSecret: process.env.JWT_SECRET
  }
};