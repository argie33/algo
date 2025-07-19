/**
 * Integration Test Setup
 * Runs before all integration tests to configure the environment
 */

// Set test environment
process.env.NODE_ENV = 'test'

// Database configuration for tests
process.env.DB_HOST = process.env.TEST_DB_HOST || process.env.DB_HOST || 'localhost'
process.env.DB_PORT = process.env.TEST_DB_PORT || process.env.DB_PORT || '5432'
process.env.DB_USER = process.env.TEST_DB_USER || process.env.DB_USER || 'postgres'
process.env.DB_PASSWORD = process.env.TEST_DB_PASSWORD || process.env.DB_PASSWORD || 'password'
process.env.DB_NAME = process.env.TEST_DB_NAME || process.env.DB_NAME || 'stocks'

// API configuration for tests
process.env.API_URL = process.env.TEST_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'

// Disable SSL for test database connections
process.env.DB_SSL = 'false'

// Increase timeout for integration tests
jest.setTimeout(30000)

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