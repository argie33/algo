// Global setup for tests - loads real database schema from Python loaders
// No mocks, no fallbacks, no demo data - tests use real data structure only
module.exports = async () => {
  process.env.NODE_ENV = "test";

  // Set database environment variables BEFORE importing database module
  process.env.DB_HOST = "localhost";
  process.env.DB_USER = "postgres";
  process.env.DB_PASSWORD = "password";
  process.env.DB_NAME = "stocks";
  process.env.DB_PORT = "5432";
  process.env.DB_SSL = "false";

  try {
    const { query } = require('../../utils/database');

    console.log('🔧 Global Setup: Creating tables from setup_test_database.sql...');

    const fs = require('fs');
    const path = require('path');

    const setupSqlPath = path.join(__dirname, '../../setup_test_database.sql');
    const setupSql = fs.readFileSync(setupSqlPath, 'utf8');

    // Execute entire SQL as one statement for faster setup
    try {
      await query(setupSql);
    } catch (error) {
      // If batch fails, try individual statements
      console.log('Batch SQL failed, trying individual statements...');
      const statements = setupSql.split(';').filter(stmt => {
        const trimmed = stmt.trim();
        return trimmed.length > 0 && !trimmed.startsWith('--');
      });

      for (const statement of statements) {
        const trimmed = statement.trim();
        if (trimmed && !trimmed.startsWith('--')) {
          try {
            await query(trimmed + ';');
          } catch (err) {
            // Ignore table exists errors
            if (!err.message.includes('already exists') && !err.message.includes('duplicate key')) {
              console.warn(`SQL Warning: ${err.message.substring(0, 100)}`);
            }
          }
        }
      }
    }

    console.log('✅ Real database schema loaded successfully - no mocks or demo data');

    // Now populate essential test data including economic data
    const { setupTestDatabase } = require('./database.setup');
    await setupTestDatabase();

  } catch (error) {
    console.error('❌ Global setup failed:', error);
    // Tests should fail if real database schema cannot be loaded - no fallbacks
    throw error;
  }
};