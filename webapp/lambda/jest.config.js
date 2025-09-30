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
  // setupFilesAfterEnv: ["<rootDir>/tests/setup.js"], // Temporarily disable setup
  testTimeout: 30000, // Increased timeout for stability
  maxWorkers: 1, // Run tests serially to avoid conflicts
  forceExit: true, // Force exit after tests complete
  detectOpenHandles: true, // Enable to detect hanging handles
  openHandlesTimeout: 5000, // Timeout for detecting open handles
  verbose: true, // Show test details for debugging
  silent: false,
  bail: false, // Don't stop on first failure
  // DISABLE COMPLEX GLOBAL SETUP TO PREVENT HANGING
  // globalSetup: "<rootDir>/tests/setup/globalSetup.js",
  // globalTeardown: "<rootDir>/tests/setup/globalTeardown.js",
  // Improved isolation settings
  clearMocks: true,
  resetMocks: true,
  restoreMocks: true,
  // Environment variables for testing
  testEnvironmentOptions: {
    NODE_ENV: "test",
  },
};
