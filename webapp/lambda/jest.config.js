module.exports = {
  testEnvironment: "node",
  // Use real database - NO MOCKS - full integration testing
  collectCoverage: false, // Disable coverage for speed - enable only for final validation
  coverageDirectory: "coverage",
  coverageReporters: ["text", "lcov", "html"],
  collectCoverageFrom: [
    "utils/**/*.js",
    "routes/**/*.js",
    "middleware/**/*.js",
    "handlers/**/*.js",
    "services/**/*.js",
    "!**/node_modules/**",
    "!tests/**",
    "!coverage/**",
  ],
  testMatch: ["**/tests/**/*.test.js", "**/tests/**/*.spec.js"],
  // Only ignore node_modules - all integration and e2e tests use REAL database
  testPathIgnorePatterns: [
    "/node_modules/",
  ],
  // NO SETUP - use real database directly
  testTimeout: 60000, // 60s timeout for real database queries
  maxWorkers: 1, // Serial execution to avoid connection pool exhaustion
  forceExit: true, // Force exit after tests complete
  detectOpenHandles: false, // Disable for speed
  openHandlesTimeout: 5000,
  verbose: true, // Show all test details
  silent: false,
  bail: false, // Don't stop on first failure - see all issues
  // NO GLOBAL SETUP - use real database as-is
  // Isolation settings for real database
  clearMocks: false, // Don't clear real database connections
  resetMocks: false, // Don't reset real database functions
  restoreMocks: false, // Don't restore real database state
  // Environment variables for testing against real database
  testEnvironmentOptions: {
    NODE_ENV: "test", // Use test config for graceful error handling
  },
};
