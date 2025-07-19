module.exports = {
  testEnvironment: 'node',
  testMatch: [
    '**/tests/integration/**/*.test.js',
    '**/tests/integration/**/*.spec.js'
  ],
  testPathIgnorePatterns: [
    '/node_modules/',
    '/tests/unit/',
    '/tests/e2e/'
  ],
  setupFilesAfterEnv: ['<rootDir>/tests/setup/integration-setup.js'],
  collectCoverageFrom: [
    'utils/**/*.js',
    'routes/**/*.js',
    'services/**/*.js',
    'middleware/**/*.js',
    '!**/node_modules/**',
    '!**/tests/**',
    '!**/coverage/**'
  ],
  coverageDirectory: 'test-results/integration-coverage',
  coverageReporters: ['text', 'lcov', 'json', 'html'],
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 60,
      lines: 60,
      statements: 60
    }
  },
  testTimeout: 30000, // 30 seconds for integration tests
  verbose: true,
  forceExit: true,
  detectOpenHandles: true,
  // Report configuration
  reporters: [
    'default',
    ['jest-junit', {
      outputDirectory: './test-results',
      outputName: 'integration-junit.xml',
      suiteName: 'Backend Integration Tests'
    }]
  ],
  // Run integration tests sequentially
  maxWorkers: 1,
  // Retry flaky tests
  retry: 2
}