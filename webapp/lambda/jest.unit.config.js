module.exports = {
  testEnvironment: "node",
  collectCoverage: false, // Disable for faster test runs
  coverageDirectory: "coverage",
  coverageReporters: ["text", "lcov", "html"],
  testMatch: ["**/tests/unit/**/*.test.js", "**/tests/unit/**/*.spec.js"],
  // NO GLOBAL SETUP FOR UNIT TESTS - use mocks instead
  testTimeout: 10000,
  maxWorkers: 1,
  forceExit: true,
  detectOpenHandles: false,
  openHandlesTimeout: 5000,
  verbose: true, // Show test details
  silent: false,
  bail: false,
  clearMocks: true,
  resetMocks: true,
  restoreMocks: true,
  testEnvironmentOptions: {
    NODE_ENV: "test",
  },
};
