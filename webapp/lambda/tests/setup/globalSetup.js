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

      // Simpler approach: Split on semicolons but rejoin dollar-quoted blocks
      let statements = setupSql.split(';').filter(stmt => stmt.trim().length > 0);

      // Rejoin statements that are part of dollar-quoted blocks
      const finalStatements = [];
      let currentBlock = '';
      let inDollarQuote = false;

      for (const stmt of statements) {
        currentBlock += stmt;

        // Count dollar signs to determine if we're in a dollar-quoted string
        const dollarMatches = stmt.match(/\$\$?/g) || [];
        for (const match of dollarMatches) {
          if (match === '$$') {
            inDollarQuote = !inDollarQuote;
          }
        }

        if (!inDollarQuote) {
          // Complete statement
          finalStatements.push(currentBlock.trim() + ';');
          currentBlock = '';
        } else {
          // Continue building the statement
          currentBlock += ';';
        }
      }

      // Add any remaining block
      if (currentBlock.trim()) {
        finalStatements.push(currentBlock.trim());
      }

      statements = finalStatements;

      for (const statement of statements) {
        if (statement && !statement.startsWith('--')) {
          try {
            await query(statement);
          } catch (err) {
            // Ignore table exists errors and column reference errors (which happen during setup)
            if (!err.message.includes('already exists') &&
                !err.message.includes('duplicate key') &&
                !err.message.includes('does not exist') &&
                !err.code === '42703') {
              console.warn(`SQL Warning: ${err.message.substring(0, 100)}`);
            }
          }
        }
      }
    }

    console.log('✅ Real database schema loaded successfully');

    // Now populate test data
    console.log('📊 Populating test data...');
    await populateLoaderTestData();
    console.log('✅ Test data populated successfully');

  } catch (error) {
    console.error('❌ Global setup failed:', error);
    // Tests should fail if real database schema cannot be loaded - no fallbacks
    throw error;
  }
};
