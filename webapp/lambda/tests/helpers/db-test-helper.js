/**
 * Database Test Helper
 * Provides utilities for setting up and tearing down test data
 */

const { Pool } = require('pg');

let testPool = null;

/**
 * Initialize test database pool (use existing connection from database.js)
 */
async function initTestDb() {
  const db = require('../../utils/database');
  return db.pool || await db.initializeDatabase();
}

/**
 * Clear all tables in test database (truncate)
 */
async function clearDatabase() {
  try {
    const db = require('../../utils/database');
    const pool = db.pool;

    if (!pool) {
      throw new Error('Database pool not initialized');
    }

    const client = await pool.connect();

    try {
      // Get all table names
      const result = await client.query(`
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
      `);

      const tables = result.rows.map(r => r.tablename);

      // Disable foreign key checks
      await client.query('SET session_replication_role = replica');

      // Truncate all tables
      for (const table of tables) {
        try {
          await client.query(`TRUNCATE TABLE ${table} CASCADE`);
        } catch (e) {
          // Skip system tables that can't be truncated
          if (!e.message.includes('cannot truncate')) {
            console.warn(`Warning truncating ${table}:`, e.message);
          }
        }
      }

      // Re-enable foreign key checks
      await client.query('SET session_replication_role = DEFAULT');

      console.log(`✅ Cleared ${tables.length} tables from test database`);
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('Error clearing database:', error.message);
    throw error;
  }
}

/**
 * Insert test data fixtures
 */
async function insertTestData() {
  try {
    const db = require('../../utils/database');
    const pool = db.pool;

    if (!pool) {
      throw new Error('Database pool not initialized');
    }

    const client = await pool.connect();

    try {
      // Insert test stocks
      await client.query(`
        INSERT INTO stock_symbols (symbol, company_name, sector, industry, market_cap)
        VALUES
          ('TEST1', 'Test Company 1', 'Technology', 'Software', 1000000000),
          ('TEST2', 'Test Company 2', 'Healthcare', 'Pharmaceuticals', 500000000)
        ON CONFLICT (symbol) DO NOTHING
      `);

      // Insert test price data
      await client.query(`
        INSERT INTO price_daily (symbol, date, open, high, low, close, volume, adjusted_close)
        VALUES
          ('TEST1', CURRENT_DATE - INTERVAL '30 days', 100, 105, 99, 104, 1000000, 104),
          ('TEST1', CURRENT_DATE - INTERVAL '29 days', 104, 108, 103, 107, 1100000, 107),
          ('TEST1', CURRENT_DATE - INTERVAL '1 day', 107, 110, 106, 109, 1200000, 109),
          ('TEST1', CURRENT_DATE, 109, 112, 108, 111, 1300000, 111),
          ('TEST2', CURRENT_DATE - INTERVAL '30 days', 50, 52, 49, 51, 500000, 51),
          ('TEST2', CURRENT_DATE, 51, 53, 50, 52, 550000, 52)
        ON CONFLICT DO NOTHING
      `);

      // Insert test technical data
      await client.query(`
        INSERT INTO technical_data_daily (symbol, date, rsi, macd, sma_20, sma_50)
        VALUES
          ('TEST1', CURRENT_DATE, 65, 1.5, 105, 103),
          ('TEST2', CURRENT_DATE, 55, 0.5, 51, 50)
        ON CONFLICT DO NOTHING
      `);

      // Insert test earnings data
      await client.query(`
        INSERT INTO earnings (symbol, report_date, actual_eps)
        VALUES
          ('TEST1', CURRENT_DATE - INTERVAL '90 days', 2.5),
          ('TEST1', CURRENT_DATE - INTERVAL '180 days', 2.3),
          ('TEST2', CURRENT_DATE - INTERVAL '90 days', 1.0),
          ('TEST2', CURRENT_DATE - INTERVAL '180 days', 0.9)
        ON CONFLICT DO NOTHING
      `);

      console.log('✅ Test data inserted');
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('Error inserting test data:', error.message);
    throw error;
  }
}

/**
 * Reset test database to clean state
 */
async function resetTestDatabase() {
  await clearDatabase();
  await insertTestData();
}

module.exports = {
  initTestDb,
  clearDatabase,
  insertTestData,
  resetTestDatabase,
};
