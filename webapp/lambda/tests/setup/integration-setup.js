/**
 * Integration Test Setup (Industry Standard)
 * Runs before all integration tests to configure real AWS environment
 */

// Set test environment
process.env.NODE_ENV = 'test'

// Integration test configuration
process.env.USE_REAL_AWS = 'true'
process.env.INTEGRATION_TEST = 'true'

// Disable automatic service initialization during tests
process.env.DISABLE_AUTO_SERVICES = 'true'
process.env.DISABLE_PATTERN_DETECTION = 'true'
process.env.DISABLE_BACKGROUND_TASKS = 'true'

// AWS Region configuration
process.env.AWS_REGION = process.env.AWS_REGION || 'us-east-1'

// Database configuration for AWS integration tests
// Note: Real values come from CloudFormation stack outputs
if (process.env.TEST_DB_SECRET_ARN) {
  // Using real AWS infrastructure with Secrets Manager
  console.log('🔧 Using real AWS infrastructure for integration tests')
} else {
  // Fallback to local configuration for development
  console.log('⚠️ Using fallback configuration - real AWS infrastructure not available')
  process.env.DB_HOST = process.env.TEST_DB_HOST || process.env.DB_HOST || 'localhost'
  process.env.DB_PORT = process.env.TEST_DB_PORT || process.env.DB_PORT || '5432'
  process.env.DB_USER = process.env.TEST_DB_USER || process.env.DB_USER || 'postgres'
  process.env.DB_PASSWORD = process.env.TEST_DB_PASSWORD || process.env.DB_PASSWORD || 'password'
  process.env.DB_NAME = process.env.TEST_DB_NAME || process.env.DB_NAME || 'stocks_test'
}

// API configuration for tests
process.env.API_URL = process.env.TEST_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'

// SSL configuration for test environments
process.env.DB_SSL = 'false'

// Authentication configuration for integration tests
process.env.ALLOW_DEV_AUTH_BYPASS = 'false' // Use real auth in integration tests
process.env.JWT_SECRET = 'test-jwt-secret' // Use consistent JWT secret for tests
process.env.API_KEY_ENCRYPTION_SECRET = 'test-encryption-secret' // Use consistent encryption secret for tests

// Timeout configuration for AWS operations
jest.setTimeout(120000) // 2 minutes for AWS operations

// Global test utilities
global.testUtils = {
  // Helper to create test user ID
  createTestUserId: () => `test-user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
  
  // Helper to create test portfolio ID
  createTestPortfolioId: () => `test-portfolio-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
  
  // Helper to wait for async operations
  wait: (ms) => new Promise(resolve => setTimeout(resolve, ms)),
  
  // Helper to retry operations
  retry: async (fn, retries = 3, delay = 1000) => {
    for (let i = 0; i < retries; i++) {
      try {
        return await fn()
      } catch (error) {
        if (i === retries - 1) throw error
        await global.testUtils.wait(delay)
      }
    }
  }
}

// Setup logging for tests
const originalConsole = console
global.console = {
  ...console,
  log: process.env.DEBUG_TESTS === 'true' ? originalConsole.log : () => {},
  debug: process.env.DEBUG_TESTS === 'true' ? originalConsole.debug : () => {},
  info: process.env.DEBUG_TESTS === 'true' ? originalConsole.info : () => {},
  warn: originalConsole.warn,
  error: originalConsole.error
}

console.log('🧪 Integration test environment configured')
console.log(`📊 Database: ${process.env.DB_HOST}:${process.env.DB_PORT}/${process.env.DB_NAME}`)
console.log(`🌐 API URL: ${process.env.API_URL}`)

// Global cleanup for tests
afterAll(async () => {
  console.log('🧹 Cleaning up integration test environment...')
  
  // Close any open database connections
  if (global.testPool) {
    await global.testPool.end()
  }
  
  console.log('✅ Integration test cleanup complete')
})