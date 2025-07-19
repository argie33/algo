/**
 * Jest Configuration for CI/CD Integration Tests
 * Handles real-world CI/CD environment constraints
 */

module.exports = {
  testEnvironment: 'node',
  
  // Test discovery
  testMatch: [
    '**/tests/integration/ci-cd-real-integration.test.js',
    '**/tests/integration/infrastructure-validation.test.js'
  ],
  
  // Setup files
  setupFilesAfterEnv: ['<rootDir>/tests/ci-cd-setup.js'],
  
  // Coverage configuration
  collectCoverageFrom: [
    'utils/**/*.js',
    'routes/**/*.js',
    'middleware/**/*.js',
    '!**/node_modules/**',
    '!**/tests/**'
  ],
  
  // Coverage directory and reporters
  coverageDirectory: 'coverage-integration',
  coverageReporters: ['text', 'lcov', 'html', 'json'],
  
  // Test timeout - longer for CI/CD environments
  testTimeout: 30000,
  
  // Reporters for CI/CD
  reporters: [
    'default',
    ['jest-junit', {
      outputDirectory: './test-results',
      outputName: 'ci-cd-integration-junit.xml',
      classNameTemplate: '{classname}',
      titleTemplate: '{title}',
      ancestorSeparator: ' › ',
      usePathForSuiteName: true
    }]
  ],
  
  // Module handling for CI/CD environments
  moduleNameMapper: {
    // Handle potential module resolution issues
    '^@/(.*)$': '<rootDir>/$1'
  },
  
  // Transform configuration
  transform: {
    '^.+\\.js$': 'babel-jest'
  },
  
  // Ignore patterns
  transformIgnorePatterns: [
    'node_modules/(?!(supertest|@aws-sdk)/)'
  ],
  
  // Clear mocks between tests
  clearMocks: true,
  
  // Collect coverage
  collectCoverage: true,
  
  // Exit on test completion
  forceExit: true,
  
  // Detect open handles
  detectOpenHandles: true,
  
  // Verbose output for CI/CD debugging
  verbose: true,
  
  // Note: runInBand should be passed as CLI option, not config
  
  // Global setup and teardown
  globalSetup: undefined,
  globalTeardown: undefined,
  
  // Error handling
  errorOnDeprecated: false,
  
  // Handle large test outputs
  maxWorkers: 1,
  
  // Cache directory
  cacheDirectory: '<rootDir>/.jest-cache',
  
  // Mock configuration
  automock: false,
  
  // Module directories
  moduleDirectories: ['node_modules', '<rootDir>'],
  
  // Test path ignore patterns
  testPathIgnorePatterns: [
    '/node_modules/',
    '/coverage/',
    '/test-results/'
  ],
  
  // Watch ignore patterns
  watchPathIgnorePatterns: [
    '/node_modules/',
    '/coverage/',
    '/test-results/'
  ]
};