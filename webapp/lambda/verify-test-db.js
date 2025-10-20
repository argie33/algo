#!/usr/bin/env node
/**
 * Verify test database configuration
 */

const path = require('path');
// Don't load .env - we want to simulate Jest setup which forces stocks_test

console.log('\n' + '='.repeat(70));
console.log('VERIFYING TEST DATABASE CONFIGURATION');
console.log('='.repeat(70) + '\n');

// Set test environment (simulate jest.setup.js behavior)
process.env.NODE_ENV = 'test';
process.env.DB_HOST = 'localhost';
process.env.DB_PORT = '5432';
process.env.DB_USER = 'postgres';
process.env.DB_PASSWORD = 'password';
process.env.DB_NAME = 'stocks_test'; // FORCE test database like Jest does
process.env.DB_SSL = 'false';

console.log('Environment Configuration:');
console.log('  NODE_ENV:', process.env.NODE_ENV);
console.log('  DB_HOST:', process.env.DB_HOST);
console.log('  DB_PORT:', process.env.DB_PORT);
console.log('  DB_NAME:', process.env.DB_NAME);
console.log('  DB_USER:', process.env.DB_USER);
console.log('');

// Test connection
const { Pool } = require('pg');

const config = {
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT) || 5432,
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'password',
  database: process.env.DB_NAME,
};

console.log('Testing connection to:', `${config.host}:${config.port}/${config.database}`);

const pool = new Pool(config);

pool.query('SELECT NOW() as current_time')
  .then(() => {
    console.log('✅ Database connection successful\n');
    return pool.query(`
      SELECT
        COUNT(*) as table_count
      FROM information_schema.tables
      WHERE table_schema = 'public'
    `);
  })
  .then(result => {
    console.log('Database Schema:');
    console.log('  Tables:', result.rows[0].table_count);

    return pool.query(`
      SELECT
        COUNT(*) as row_count,
        COUNT(DISTINCT symbol) as symbols
      FROM stock_scores
    `);
  })
  .then(result => {
    console.log('  stock_scores records:', result.rows[0].row_count);
    console.log('  stock_scores symbols:', result.rows[0].symbols);
    console.log('');

    console.log('✅ Test Database Configuration: VALID');
    console.log('   Ready to run integration tests against real database\n');
  })
  .catch(error => {
    console.error('❌ Configuration Error:', error.message);
    process.exit(1);
  })
  .finally(() => {
    pool.end();
  });
