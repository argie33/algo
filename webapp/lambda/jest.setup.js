/**
 * Jest Setup File
 * Initializes database connection pool and environment before any tests run
 */

// Load environment variables
require('dotenv').config();

// Set test environment
process.env.NODE_ENV = "test";
process.env.ALLOW_DEV_BYPASS = "true";
process.env.JWT_SECRET = "test-secret-key-for-testing-only";

// Set database connection environment variables FOR TESTS
// IMPORTANT: Tests use stocks database - same database as loaders
// All tests point to same database where data is loaded
if (!process.env.DB_HOST) process.env.DB_HOST = "localhost";
if (!process.env.DB_PORT) process.env.DB_PORT = "5432";
if (!process.env.DB_USER) process.env.DB_USER = "postgres";
if (!process.env.DB_PASSWORD) process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks"; // Use stocks database - same as loaders (override any .env setting)
if (!process.env.DB_SSL) process.env.DB_SSL = "false";

console.log('\n🔧 Jest setup file loaded');
console.log(`Database config: ${process.env.DB_HOST}:${process.env.DB_PORT}/${process.env.DB_NAME}`);

// Load database module at top level to ensure it's available in Jest environment
const db = require('./utils/database');

// Initialize database connection pool before any tests run
beforeAll(async () => {
  try {
    console.log('🔧 Initializing database connection pool...');
    // Initialize database connection pool
    await db.initializeDatabase();
    console.log('✅ Database connection pool initialized successfully');
  } catch (error) {
    console.error('❌ Failed to initialize database:', error.message);
    process.exit(1);
  }
}, 60000); // 60 second timeout for initialization

// Cleanup after tests complete
afterAll(async () => {
  try {
    if (typeof db.closeDatabase === 'function') {
      console.log('🔧 Closing database connection pool...');
      await db.closeDatabase();
      console.log('✅ Database connection pool closed');
    }
  } catch (error) {
    console.error('Warning: Error closing database:', error.message);
  }
}, 30000); // 30 second timeout for cleanup
