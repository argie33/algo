import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    // Define complete Vite environment variables for tests
    "import.meta.env": {
      DEV: false,
      PROD: true,
      MODE: "test",
      VITE_FORCE_DEV_AUTH: "false",
      BASE_URL: "/",
      SSR: false
    },
    // Disable React concurrent features
    "__DEV__": true,
    "process.env.NODE_ENV": '"test"'
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.js"],
    globals: true,
    testTimeout: 30000, // Increased timeout for complex component tests
    hookTimeout: 10000, // Increased hook timeout
    teardownTimeout: 5000, // Increased cleanup time
    // Optimize pool configuration for better resource management
    pool: "forks",
    poolOptions: {
      forks: {
        singleFork: true, // Use single fork to prevent resource conflicts
        minForks: 1,
        maxForks: 1, // Single threaded execution
      },
    },
    // Test file patterns
    include: ["src/tests/**/*.{test,spec}.{js,jsx}"],
    exclude: ["node_modules/", "dist/", ".git/", "**/*.backup", "**/*.old", "**/backup/**"],
    // Reduced console output but not silent
    silent: false,
    logLevel: "error", // Only show errors
    // Custom environment options
    env: {
      NODE_ENV: 'test',
      VITE_FORCE_DEV_AUTH: 'false',
    },
    // Fix deprecated reporter
    reporters: [["default", { summary: false }]],
    // Allow limited parallelism for better resource usage
    fileParallelism: true,
    maxConcurrency: 1, // Single test at a time to prevent conflicts
    // No retries to speed up
    retry: 0,
    // Aggressive cleanup
    restoreMocks: true,
    clearMocks: true,
    resetMocks: true,
    // Disable coverage to speed up
    coverage: {
      enabled: false,
    },
    // Add memory management
    maxWorkers: 2,
    isolate: true, // Better isolation between tests
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});
