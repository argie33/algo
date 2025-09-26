module.exports = {
  testEnvironment: "node",
  collectCoverage: false, // Disable during development for speed
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
  setupFilesAfterEnv: ["<rootDir>/tests/setup.js"],
  testTimeout: 15000, // 15 seconds timeout - faster execution
  maxWorkers: 1, // Run tests serially to avoid conflicts
  forceExit: true, // Force exit after tests complete
  detectOpenHandles: false, // Disable for better performance
  verbose: true, // Show test details for debugging
  silent: false,
  bail: false, // Don't stop on first failure
  // Mock console by default to reduce test noise
  globalSetup: "<rootDir>/tests/setup/globalSetup.js",
  globalTeardown: "<rootDir>/tests/setup/globalTeardown.js",
  // Environment variables for testing
  testEnvironmentOptions: {
    NODE_ENV: "test",
  },
};
