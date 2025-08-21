module.exports = {
  testEnvironment: 'node',
  collectCoverage: false, // Disable during development for speed
  coverageDirectory: 'coverage',
  coverageReporters: ['text', 'lcov', 'html'],
  collectCoverageFrom: [
    'utils/**/*.js',
    'routes/**/*.js', 
    'middleware/**/*.js',
    'handlers/**/*.js',
    'services/**/*.js',
    '!**/node_modules/**',
    '!tests/**',
    '!coverage/**'
  ],
  testMatch: [
    '**/tests/**/*.test.js',
    '**/tests/**/*.spec.js'
  ],
  setupFilesAfterEnv: ['<rootDir>/tests/setup.js'],
  testTimeout: 30000, // 30 seconds timeout
  maxWorkers: 1, // Run tests serially to avoid conflicts
  forceExit: true, // Force exit after tests complete
  detectOpenHandles: true, // Detect async operations preventing exit
  verbose: false, // Reduce noise during testing
  silent: false,
  // Mock console by default to reduce test noise
  globalSetup: '<rootDir>/tests/globalSetup.js',
  globalTeardown: '<rootDir>/tests/globalTeardown.js',
  // Environment variables for testing
  testEnvironmentOptions: {
    NODE_ENV: 'test'
  }
};