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
  testMatch: ["**/tests/unit/**/*.test.js", "**/tests/unit/**/*.spec.js"],
  // NO setupFilesAfterEnv - unit tests should not connect to real database
  testTimeout: 25000, // Increased for mock-based unit tests
  maxWorkers: 1,
  forceExit: true,
  detectOpenHandles: true,
  verbose: false,
  silent: false,
  // NO globalSetup or globalTeardown - unit tests are isolated
  testEnvironmentOptions: {
    NODE_ENV: "test",
  },
  // Ensure mocks work properly
  clearMocks: true,
  resetMocks: true,
  restoreMocks: true,
};