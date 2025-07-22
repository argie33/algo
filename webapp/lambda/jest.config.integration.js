/**
 * Jest Configuration for REAL Integration Tests
 * NO MOCKS - Real database, real services, real everything
 */

module.exports = {
  // Test environment
  testEnvironment: 'node',
  
  // Test patterns - only integration tests
  testMatch: [
    '**/tests/integration/**/*.test.js'
  ],
  
  // Setup files
  setupFilesAfterEnv: [
    '<rootDir>/tests/integration-setup.js'
  ],
  
  // Environment variables
  setupFiles: [
    '<rootDir>/scripts/load-test-env.js'
  ],
  
  // Global setup and teardown for real database
  globalSetup: '<rootDir>/tests/integration-global-setup.js',
  globalTeardown: '<rootDir>/tests/integration-global-teardown.js',
  
  // Test timeout for real operations
  testTimeout: 30000,
  
  // Run tests serially to avoid database conflicts
  maxWorkers: 1,
  
  // Coverage configuration
  collectCoverage: false, // Disable for integration tests
  
  // Clear mocks between tests (but we're using real services)
  clearMocks: false,
  resetMocks: false,
  restoreMocks: false,
  
  // Module path mapping
  moduleNameMapping: {
    '^@/(.*)$': '<rootDir>/$1',
    '^@utils/(.*)$': '<rootDir>/utils/$1',
    '^@services/(.*)$': '<rootDir>/services/$1',
    '^@middleware/(.*)$': '<rootDir>/middleware/$1'
  },
  
  // Verbose output for debugging
  verbose: true,
  
  // Transform configuration
  transform: {
    '^.+\\.js$': 'babel-jest'
  },
  
  // Module file extensions
  moduleFileExtensions: ['js', 'json'],
  
  // Test reporter
  reporters: [
    'default'
  ],
  
  // Force exit after tests complete
  forceExit: true,
  
  // Detect open handles (for debugging connection leaks)
  detectOpenHandles: true,
  
  // Don't transform node_modules
  transformIgnorePatterns: [
    'node_modules/(?!(@babel/runtime)/)'
  ]
};