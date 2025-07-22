/**
 * Load Real Integration Test Environment Variables
 * Sets up environment for real database and service testing
 */

const path = require('path');
const fs = require('fs');

// Load test environment variables
const testEnvPath = path.join(__dirname, '../test.env');

if (fs.existsSync(testEnvPath)) {
  console.log('🔧 Loading real integration test environment...');
  
  const envContent = fs.readFileSync(testEnvPath, 'utf8');
  const envVars = envContent
    .split('\n')
    .filter(line => line.trim() && !line.startsWith('#'))
    .map(line => line.split('='))
    .filter(([key, value]) => key && value !== undefined);
  
  envVars.forEach(([key, value]) => {
    if (!process.env[key]) {
      process.env[key] = value;
    }
  });
  
  console.log('✅ Real integration test environment loaded');
  console.log('Database:', process.env.DB_HOST + ':' + process.env.DB_PORT + '/' + process.env.DB_NAME);
} else {
  console.warn('⚠️ Test environment file not found, using default values');
  
  // Set default real test values
  process.env.NODE_ENV = 'test';
  process.env.DB_HOST = 'localhost';
  process.env.DB_PORT = '5432';
  process.env.DB_NAME = 'financial_platform_test';
  process.env.DB_USER = 'postgres';
  process.env.DB_PASS = '';
  process.env.DB_SSL = 'false';
  process.env.JWT_SECRET = 'test-jwt-secret';
}

// Ensure we're in test mode but using real services
process.env.NODE_ENV = 'test';
process.env.USE_REAL_DATABASE = 'true';
process.env.DISABLE_MOCKS = 'true';

console.log('🚀 Real integration test environment ready');
console.log('   NODE_ENV:', process.env.NODE_ENV);
console.log('   Database:', process.env.DB_HOST + ':' + process.env.DB_PORT);
console.log('   Using REAL database (no mocks)');