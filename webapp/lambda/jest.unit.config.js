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
  // Remove moduleNameMapper - use real database module
  testMatch: ["**/tests/unit/**/*.test.js", "**/tests/unit/**/*.spec.js"],
  setupFilesAfterEnv: ["<rootDir>/tests/setup.js"],
  testTimeout: 10000, // Reduced for mock database
  maxWorkers: 1,
  forceExit: true,
  detectOpenHandles: false,
  verbose: false,
  silent: false,
  // globalSetup: "<rootDir>/tests/setup/globalSetup.js",
  // globalTeardown: "<rootDir>/tests/setup/globalTeardown.js",
  testEnvironmentOptions: {
    NODE_ENV: "test",
  },
  // Clear mocks but allow real database connections
  clearMocks: true,
  resetMocks: false, // Keep real database module
  restoreMocks: false
};
