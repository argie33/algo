module.exports = {
  testEnvironment: "node",
  collectCoverage: false,
  testMatch: ["**/tests/integration/**/*.test.js", "**/tests/integration/**/*.spec.js"],
  // Include integration tests - don't ignore them
  testPathIgnorePatterns: [
    "/node_modules/",
  ],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
  testTimeout: 60000,
  maxWorkers: 1,
  forceExit: true,
  detectOpenHandles: false,
  openHandlesTimeout: 5000,
  verbose: true,
  silent: false,
  bail: false,
  clearMocks: false,
  resetMocks: false,
  restoreMocks: false,
  testEnvironmentOptions: {
    NODE_ENV: "test",
  },
};
