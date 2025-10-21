module.exports = {
  testEnvironment: "node",
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
  testMatch: ["**/tests/unit/**/*.test.js", "**/tests/**/*.spec.js"],
  // Skip integration tests - they require full infrastructure
  testPathIgnorePatterns: [
    "/node_modules/",
    "/tests/integration/",
  ],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
  testTimeout: 60000, // 60s timeout for integration tests (real database)
  maxWorkers: 1, // Single worker for database consistency
  forceExit: true, // Force exit after tests complete
  detectOpenHandles: false, // Disable for speed
  openHandlesTimeout: 5000,
  verbose: true, // Show all test details
  silent: false,
  bail: false, // Don't stop on first failure - see all issues
  // Mock configuration (conservative)
  clearMocks: false,
  resetMocks: false,
  restoreMocks: false,
  // Environment variables for testing
  testEnvironmentOptions: {
    NODE_ENV: "test", // Use test config for graceful error handling
  },
};
