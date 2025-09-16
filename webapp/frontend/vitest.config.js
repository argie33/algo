import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    // Define Vite environment variables for tests to match development mode
    "import.meta.env.DEV": true,
    "import.meta.env.PROD": false,
    "import.meta.env.MODE": '"test"',
    // Disable React concurrent features
    "__DEV__": true,
    "process.env.NODE_ENV": '"test"'
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/simple-setup.js"],
    globals: true,
    testTimeout: 15000, // Reduced to catch hanging tests faster
    hookTimeout: 10000, // Reduced hook timeout
    teardownTimeout: 5000, // Reduced cleanup time
    // Use single thread to avoid race conditions
    pool: "threads",
    poolOptions: {
      threads: {
        singleThread: true,
        minThreads: 1,
        maxThreads: 1,
      },
    },
    // Test file patterns - allow targeting specific files
    include: ["src/tests/**/*.{test,spec}.{js,jsx}"],
    exclude: ["node_modules/", "dist/", ".git/", "**/*.backup", "**/*.old", "**/backup/**"],
    // Less restrictive console output for debugging
    silent: false,
    // Custom environment options
    env: {
      NODE_ENV: 'test',
    },
    // Standard reporters
    reporters: ["default"],
    // Disable parallel execution to reduce resource contention
    fileParallelism: false,
    // Allow retries for flaky React component tests
    retry: 1,
    // Cleanup options
    restoreMocks: true,
    clearMocks: true,
    resetMocks: true,
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});
