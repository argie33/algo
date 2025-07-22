/**
 * Jest Configuration for Unit Tests with S3 Upload Support
 * Generates all required output files for S3 upload workflow
 */

module.exports = {
  // Test environment
  testEnvironment: 'node',
  
  // Test patterns - only unit tests
  testMatch: [
    '**/tests/unit/**/*.test.js'
  ],
  
  // Setup files
  setupFilesAfterEnv: [
    '<rootDir>/tests/setup.js'
  ],
  
  // Test timeout
  testTimeout: 120000,
  
  // Coverage configuration for S3 upload
  collectCoverage: true,
  collectCoverageFrom: [
    'utils/**/*.js',
    'services/**/*.js',
    'middleware/**/*.js',
    'routes/**/*.js',
    '!**/node_modules/**',
    '!**/tests/**',
    '!**/coverage/**'
  ],
  coverageDirectory: 'coverage',
  coverageReporters: [
    'json',           // For coverage-final.json
    'json-summary',   // For coverage summary
    'lcov',           // For detailed coverage
    'text',           // For console output
    'clover'          // Alternative format
  ],
  
  // JUnit reporter for S3 upload
  reporters: [
    'default',
    ['jest-junit', {
      outputDirectory: '.',
      outputName: 'junit.xml',
      suiteName: 'Unit Tests',
      classNameTemplate: '{classname}',
      titleTemplate: '{title}',
      ancestorSeparator: ' › ',
      usePathForSuiteName: true
    }]
  ],
  
  // JSON test results for S3 upload
  testResultsProcessor: '<rootDir>/scripts/process-unit-test-results.js',
  
  // Verbose output
  verbose: true,
  
  // Transform configuration
  transform: {
    '^.+\\.js$': 'babel-jest'
  },
  
  // Module file extensions
  moduleFileExtensions: ['js', 'json'],
  
  // Don't transform node_modules
  transformIgnorePatterns: [
    'node_modules/(?!(@babel/runtime)/)'
  ],
  
  // Clear mocks between tests
  clearMocks: true,
  resetMocks: true,
  restoreMocks: true,
  
  // Bail after first test failure (optional)
  bail: false,
  
  // Force exit after tests complete
  forceExit: true,
  
  // Detect open handles for debugging
  detectOpenHandles: true,
  
  // Max workers for parallel execution
  maxWorkers: '50%'
};