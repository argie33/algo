// Load environment variables before any tests run
require('dotenv').config();

module.exports = {
  testEnvironment: "node",
  collectCoverage: false,
  coverageDirectory: "coverage-unit",
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
  // Use real database module - NO mock database
  testMatch: ["**/tests/unit/**/*.test.js", "**/tests/unit/**/*.spec.js"],
  setupFilesAfterEnv: ["<rootDir>/tests/setup/database.setup.js"],
  testTimeout: 30000, // Increased for real database operations
  maxWorkers: 1,
  forceExit: true,
  detectOpenHandles: false,
  verbose: false,
  silent: false,
  globalSetup: "<rootDir>/tests/setup/globalSetup.js",
  testEnvironmentOptions: {
    NODE_ENV: "test",
  },
  // Clear mocks but allow real database connections
  clearMocks: true,
  resetMocks: false, // Keep real database module
  restoreMocks: false
};
