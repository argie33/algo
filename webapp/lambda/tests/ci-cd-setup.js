/**
 * CI/CD Test Setup Configuration
 * 
 * This setup handles the real-world CI/CD environment issues:
 * - Missing database credentials
 * - No Cognito configuration 
 * - Missing AWS services
 * - Authentication bypass for testing
 */

const path = require('path');

// Load test environment variables
require('dotenv').config({ path: path.join(__dirname, '..', '.env.test') });

console.log('🧪 CI/CD Test Environment Setup');
console.log('================================');

// Set up test environment
process.env.NODE_ENV = 'test';

// Mock AWS SDK for tests
jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn(() => ({
    send: jest.fn().mockResolvedValue({
      SecretString: JSON.stringify({
        host: process.env.DB_HOST || 'localhost',
        port: process.env.DB_PORT || '5432',
        database: process.env.DB_NAME || 'financial_platform_test',
        username: process.env.DB_USER || 'postgres',
        password: process.env.DB_PASSWORD || 'postgres',
        ssl: false
      })
    })
  })),
  GetSecretValueCommand: jest.fn()
}));

// Mock Cognito for tests
jest.mock('@aws-sdk/client-cognito-identity-provider', () => ({
  CognitoIdentityProviderClient: jest.fn(() => ({
    send: jest.fn().mockResolvedValue({
      UserPoolId: 'test-user-pool',
      ClientId: 'test-client-id'
    })
  }))
}));

// Set up authentication bypass for CI/CD testing
process.env.ALLOW_TEST_AUTH_BYPASS = 'true';
process.env.JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret-for-ci-cd';
process.env.API_KEY_ENCRYPTION_SECRET = process.env.API_KEY_ENCRYPTION_SECRET || 'test-encryption-secret-32-bytes!!';

// Database configuration for CI/CD
if (!process.env.DB_HOST) {
  console.log('⚠️ No database configuration found - tests will handle connection failures');
  process.env.DB_HOST = 'localhost';
  process.env.DB_PORT = '5432';
  process.env.DB_NAME = 'financial_platform_test';
  process.env.DB_USER = 'postgres';
  process.env.DB_PASSWORD = 'postgres';
  process.env.DB_SSL = 'false';
}

// AWS configuration for tests
process.env.AWS_REGION = process.env.AWS_REGION || 'us-east-1';
process.env.DB_SECRET_ARN = process.env.DB_SECRET_ARN || 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-db-secret';
process.env.API_KEY_ENCRYPTION_SECRET_ARN = process.env.API_KEY_ENCRYPTION_SECRET_ARN || 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-encryption-secret';

// Set timeout for all tests
jest.setTimeout(30000);

// Export test configuration to global
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

// Global test setup
beforeAll(async () => {
  console.log('🔧 Global Test Setup');
  console.log(`  NODE_ENV: ${process.env.NODE_ENV}`);
  console.log(`  Database Host: ${process.env.DB_HOST}`);
  console.log(`  Database Name: ${process.env.DB_NAME}`);
  console.log(`  AWS Region: ${process.env.AWS_REGION}`);
  console.log(`  Auth Bypass: ${process.env.ALLOW_TEST_AUTH_BYPASS}`);
});

// Global test cleanup
afterAll(async () => {
  console.log('🧹 Global Test Cleanup');
  
  // Give time for async operations to complete
  await new Promise(resolve => setTimeout(resolve, 1000));
});

// Handle unhandled rejections in tests
process.on('unhandledRejection', (reason, promise) => {
  console.warn('⚠️ Unhandled Rejection in tests:', reason);
  // Don't exit - let tests handle errors gracefully
});

// Handle uncaught exceptions in tests
process.on('uncaughtException', (error) => {
  console.warn('⚠️ Uncaught Exception in tests:', error.message);
  // Don't exit - let tests handle errors gracefully
});

console.log('✅ CI/CD Test Environment Setup Complete');
console.log('================================');