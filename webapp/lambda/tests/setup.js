/**
 * Jest Test Setup Configuration
 * Sets up database connections, environment variables, and test utilities
 */

const path = require('path');

// Load environment variables for testing
require('dotenv').config({ path: path.join(__dirname, '..', '.env.test') });

// Set up test environment variables
process.env.NODE_ENV = 'test';
process.env.JWT_SECRET = 'test-jwt-secret';
process.env.API_KEY_ENCRYPTION_SECRET = 'test-encryption-secret-key-32-bytes!!';

// Database configuration for tests
process.env.DB_HOST = process.env.TEST_DB_HOST || 'localhost';
process.env.DB_PORT = process.env.TEST_DB_PORT || '5432';
process.env.DB_NAME = process.env.TEST_DB_NAME || 'financial_platform_test';
process.env.DB_USER = process.env.TEST_DB_USER || 'postgres';
process.env.DB_PASSWORD = process.env.TEST_DB_PASSWORD || 'postgres';
process.env.DB_SSL = process.env.TEST_DB_SSL || 'false';

// AWS configuration for tests (mock values)
process.env.AWS_REGION = 'us-east-1';
process.env.DB_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-db-secret';
process.env.API_KEY_ENCRYPTION_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-encryption-secret';

// Timeout configuration
jest.setTimeout(30000);

// Global test setup
beforeAll(async () => {
  // Log test environment setup
  console.log('🧪 Jest Test Environment Setup');
  console.log('- Node Environment:', process.env.NODE_ENV);
  console.log('- Database Host:', process.env.DB_HOST);
  console.log('- Database Name:', process.env.DB_NAME);
  console.log('- Database SSL:', process.env.DB_SSL);
});

// Global test cleanup
afterAll(async () => {
  // Close any remaining database connections
  console.log('🧹 Jest Test Environment Cleanup');
  
  // Give time for async operations to complete
  await new Promise(resolve => setTimeout(resolve, 1000));
});

// Mock console methods to reduce test noise (optional)
global.console = {
  ...console,
  // Uncomment to suppress logs in tests
  // log: jest.fn(),
  // info: jest.fn(),
  // warn: jest.fn(),
  // error: jest.fn(),
};

// Mock AWS SDK for tests
jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn(() => ({
    send: jest.fn().mockResolvedValue({
      SecretString: JSON.stringify({
        host: process.env.DB_HOST,
        port: process.env.DB_PORT,
        database: process.env.DB_NAME,
        username: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
        ssl: process.env.DB_SSL === 'true'
      })
    })
  })),
  GetSecretValueCommand: jest.fn()
}));

// Export test utilities
global.testConfig = {
  database: {
    host: process.env.DB_HOST,
    port: process.env.DB_PORT,
    database: process.env.DB_NAME,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    ssl: process.env.DB_SSL === 'true'
  },
  jwt: {
    secret: process.env.JWT_SECRET
  },
  encryption: {
    secret: process.env.API_KEY_ENCRYPTION_SECRET
  }
};