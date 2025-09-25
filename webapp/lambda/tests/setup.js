/**
 * Jest setup file for tests
 * Uses real PostgreSQL database with Python loader schemas
 */

// Configure environment for real database tests
process.env.NODE_ENV = 'test';
process.env.JWT_SECRET = 'test-secret-key-for-testing-only';

// Set database environment variables for real PostgreSQL connection
process.env.DB_HOST = 'localhost';
process.env.DB_USER = 'postgres';
process.env.DB_PASSWORD = 'password';
process.env.DB_NAME = 'stocks';
process.env.DB_PORT = '5432';
process.env.DB_SSL = 'false';

// Import real database connection
const { query } = require('../utils/database');

// Global setup to ensure database tables exist
beforeAll(async () => {
  try {
    // Ensure database connection is working
    await query('SELECT 1');
    console.log('✅ Real database connection established for tests');
  } catch (error) {
    console.error('❌ Failed to connect to real database:', error);
    throw error;
  }
});

// Clean up after tests if needed
afterAll(async () => {
  try {
    console.log('✅ Test cleanup complete');
  } catch (error) {
    console.error('❌ Test cleanup error:', error);
  }
});