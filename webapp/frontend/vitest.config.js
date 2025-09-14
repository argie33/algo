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
    testTimeout: 60000, // Increased for React component rendering
    hookTimeout: 30000, // Increased for complex components
    teardownTimeout: 10000, // Increased cleanup time
    // Use threads for better performance with React
    pool: "threads",
    poolOptions: {
      threads: {
        singleThread: false,
        minThreads: 1,
        maxThreads: 2,
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
    // Allow some parallel execution for efficiency
    fileParallelism: true,
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
