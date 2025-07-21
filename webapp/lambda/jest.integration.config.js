/**
 * Jest Configuration for Integration Tests
 * Industry Standard: Separate config for integration tests with real AWS services
 */

module.exports = {
  // Test environment
  testEnvironment: 'node',
  
  // Test pattern matching - REAL integration tests only
  testMatch: [
    '**/tests/integration/REAL-*.test.js'
  ],
  
  // Ignore unit tests
  testPathIgnorePatterns: [
    '/node_modules/',
    '/tests/unit/',
    '/tests/utils/',
    '/tests/setup/'
  ],
  
  // Setup files
  setupFilesAfterEnv: [
    '<rootDir>/tests/setup/integration-setup.js'
  ],
  
  // Test execution (runInBand should be passed as CLI option)
  detectOpenHandles: true,
  forceExit: true,
  
  // Timeouts for AWS operations
  testTimeout: 120000, // 2 minutes per test
  
  // Coverage (optional for integration tests)
  collectCoverage: false, // Integration tests focus on real service interactions
  
  // Reporters
  reporters: [
    'default',
    [
      'jest-junit',
      {
        outputDirectory: 'test-results',
        outputName: 'integration-junit.xml',
        suiteName: 'Integration Tests',
        classNameTemplate: 'Integration.{classname}',
        titleTemplate: '{title}',
        ancestorSeparator: ' › ',
        usePathForSuiteName: true
      }
    ]
  ],
  
  // Module configuration
  moduleDirectories: ['node_modules', '<rootDir>'],
  
  // Clear mocks between tests (important for integration tests)
  clearMocks: true,
  restoreMocks: true,
  
  // Error handling
  errorOnDeprecated: false, // AWS SDK may have deprecation warnings
  
  // Verbose output for CI/CD debugging
  verbose: true,
  
  // Environment variables for tests
  setupFiles: ['<rootDir>/tests/setup/integration-env.js'],
  
  // Global test setup/teardown
  globalSetup: '<rootDir>/tests/setup/global-integration-setup.js',
  globalTeardown: '<rootDir>/tests/setup/global-integration-teardown.js',
  
  // Transform configuration (if needed)
  transform: {},
  
  // Module name mapping (if needed for AWS SDK or other modules)
  moduleNameMapper: {},
  
  // Test result processor
  testResultsProcessor: undefined,
  
  // Watch plugins (not used in CI)
  watchPlugins: [],
  
  // Snapshot serializers
  snapshotSerializers: [],
  
  // Test sequence and bail options
  bail: 1, // Stop on first failure for faster feedback
  maxWorkers: 1, // Single worker to prevent AWS resource conflicts
  
  // Cache configuration
  cache: false, // Disable cache for integration tests to ensure fresh runs
  
  // Extensions
  moduleFileExtensions: ['js', 'json'],
  
  // Test name pattern (can be overridden via CLI)
  testNamePattern: undefined
};