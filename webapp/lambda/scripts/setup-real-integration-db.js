#!/usr/bin/env node

/**
 * Real Database Setup for Integration Tests
 * Sets up actual PostgreSQL database without mocks
 */

const { Pool } = require('pg');
const fs = require('fs');
const path = require('path');

// Real database configuration for integration tests
const DB_CONFIG = {
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT) || 5432,
  database: 'financial_platform_test',
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASS || '',
  // Real connection settings - no mocks
  ssl: false,
  max: 10, // Real connection pool
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 10000,
};

async function setupRealDatabase() {
  console.log('🚀 Setting up REAL database for integration tests...');
  console.log('Database Config:', {
    host: DB_CONFIG.host,
    port: DB_CONFIG.port,
    database: DB_CONFIG.database,
    user: DB_CONFIG.user
  });

  let adminPool = null;
  let testPool = null;

  try {
    // First connect to default postgres database to create test database
    console.log('📡 Connecting to PostgreSQL server...');
    adminPool = new Pool({
      ...DB_CONFIG,
      database: 'postgres' // Connect to default database first
    });

    // Test connection
    const client = await adminPool.connect();
    console.log('✅ Connected to PostgreSQL server');
    client.release();

    // Create test database if it doesn't exist
    console.log('🏗️ Creating test database...');
    try {
      await adminPool.query(`
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = 'financial_platform_test'
        AND pid <> pg_backend_pid()
      `);
      
      await adminPool.query('DROP DATABASE IF EXISTS financial_platform_test');
      await adminPool.query('CREATE DATABASE financial_platform_test');
      console.log('✅ Test database created');
    } catch (error) {
      if (error.message.includes('already exists')) {
        console.log('ℹ️ Test database already exists');
      } else {
        throw error;
      }
    }

    await adminPool.end();

    // Now connect to the test database
    console.log('📡 Connecting to test database...');
    testPool = new Pool(DB_CONFIG);

    const testClient = await testPool.connect();
    console.log('✅ Connected to test database');
    testClient.release();

    // Read and execute schema setup SQL
    console.log('🔧 Setting up database schema...');
    const schemaSQL = fs.readFileSync(
      path.join(__dirname, 'setup-test-database.sql'), 
      'utf8'
    );

    // Split SQL into individual statements and execute
    const statements = schemaSQL
      .split(';')
      .map(stmt => stmt.trim())
      .filter(stmt => stmt.length > 0 && !stmt.startsWith('--') && !stmt.startsWith('\\'));

    for (const statement of statements) {
      if (statement.trim()) {
        try {
          await testPool.query(statement);
        } catch (error) {
          console.warn(`⚠️ SQL statement warning: ${error.message}`);
          // Continue with other statements
        }
      }
    }

    console.log('✅ Database schema created');

    // Verify tables exist
    console.log('🔍 Verifying database setup...');
    const tablesResult = await testPool.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);

    const tables = tablesResult.rows.map(row => row.table_name);
    console.log('✅ Tables created:', tables.join(', '));

    // Verify test data
    const userCount = await testPool.query('SELECT COUNT(*) FROM users');
    const portfolioCount = await testPool.query('SELECT COUNT(*) FROM portfolio');
    const stockDataCount = await testPool.query('SELECT COUNT(*) FROM stock_data');

    console.log('✅ Test data verified:');
    console.log(`   Users: ${userCount.rows[0].count}`);
    console.log(`   Portfolio entries: ${portfolioCount.rows[0].count}`);
    console.log(`   Stock data entries: ${stockDataCount.rows[0].count}`);

    console.log('🎉 Real database setup completed successfully!');
    console.log('');
    console.log('Integration tests can now use:');
    console.log(`   Host: ${DB_CONFIG.host}:${DB_CONFIG.port}`);
    console.log(`   Database: ${DB_CONFIG.database}`);
    console.log(`   User: ${DB_CONFIG.user}`);
    console.log('');
    console.log('🚀 Ready for REAL integration testing (no mocks)!');

    return {
      success: true,
      config: DB_CONFIG,
      tables: tables,
      testDataCounts: {
        users: parseInt(userCount.rows[0].count),
        portfolio: parseInt(portfolioCount.rows[0].count),
        stockData: parseInt(stockDataCount.rows[0].count)
      }
    };

  } catch (error) {
    console.error('❌ Database setup failed:', error.message);
    console.error('Stack trace:', error.stack);
    throw error;
  } finally {
    if (adminPool) {
      await adminPool.end();
    }
    if (testPool) {
      await testPool.end();
    }
  }
}

// Run setup if called directly
if (require.main === module) {
  setupRealDatabase()
    .then(() => {
      console.log('✅ Setup completed successfully');
      process.exit(0);
    })
    .catch(error => {
      console.error('❌ Setup failed:', error.message);
      process.exit(1);
    });
}

module.exports = { setupRealDatabase, DB_CONFIG };