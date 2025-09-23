/**
 * Environment loader for test scripts
 * Ensures consistent environment setup across all test files
 */

const path = require('path');
const fs = require('fs');

// Load environment variables from .env file
const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
  require('dotenv').config({ path: envPath });
  console.log('✅ Environment loaded from .env file');
} else {
  console.log('⚠️  .env file not found, using system environment');
}

// Verify required database environment variables
const requiredEnvVars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_PORT'];
const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);

if (missingVars.length > 0) {
  console.log('❌ Missing required environment variables:', missingVars.join(', '));
  console.log('Setting default values for local development...');

  // Set default values for local development
  if (!process.env.DB_HOST) process.env.DB_HOST = 'localhost';
  if (!process.env.DB_USER) process.env.DB_USER = 'postgres';
  if (!process.env.DB_PASSWORD) process.env.DB_PASSWORD = 'password';
  if (!process.env.DB_NAME) process.env.DB_NAME = 'stocks';
  if (!process.env.DB_PORT) process.env.DB_PORT = '5432';
}

console.log('📊 Database configuration:');
console.log(`   Host: ${process.env.DB_HOST}`);
console.log(`   Port: ${process.env.DB_PORT}`);
console.log(`   Database: ${process.env.DB_NAME}`);
console.log(`   User: ${process.env.DB_USER}`);

// Run the test script passed as argument
const testScript = process.argv[2];
if (!testScript) {
  console.log('Usage: node load-env-test.js <test-script.js>');
  throw new Error('Test script argument required');
}

if (!fs.existsSync(testScript)) {
  console.log(`❌ Test script not found: ${testScript}`);
  throw new Error(`Test script not found: ${testScript}`);
}

console.log(`🚀 Running test script: ${testScript}`);
console.log('=' .repeat(50));

// Execute the test script
require(path.resolve(testScript));