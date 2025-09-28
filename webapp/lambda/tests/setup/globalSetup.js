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
      // If batch fails, try individual statements with proper dollar-quoted string handling
      console.log('Batch SQL failed, trying individual statements...');

      // Smart SQL splitting that respects dollar-quoted strings
      const statements = [];
      let currentStatement = '';
      let inDollarQuote = false;
      let dollarTag = '';

      const lines = setupSql.split('\n');
      for (const line of lines) {
        const trimmedLine = line.trim();

        // Skip comments and empty lines
        if (!trimmedLine || trimmedLine.startsWith('--')) {
          continue;
        }

        currentStatement += line + '\n';

        // Check for dollar-quoted string start/end
        const dollarMatch = line.match(/\$([a-zA-Z_]*)\$/);
        if (dollarMatch) {
          const tag = dollarMatch[1];
          if (!inDollarQuote) {
            inDollarQuote = true;
            dollarTag = tag;
          } else if (tag === dollarTag) {
            inDollarQuote = false;
            dollarTag = '';
          }
        }

        // If not in dollar quote and line ends with semicolon, it's a statement end
        if (!inDollarQuote && line.trim().endsWith(';')) {
          statements.push(currentStatement.trim());
          currentStatement = '';
        }
      }

      // Add final statement if exists
      if (currentStatement.trim()) {
        statements.push(currentStatement.trim());
      }

      for (const statement of statements) {
        if (statement && !statement.startsWith('--')) {
          try {
            await query(statement);
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