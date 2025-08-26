import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    // Define Vite environment variables for tests to match development mode
    "import.meta.env.DEV": true,
    "import.meta.env.PROD": false,
    "import.meta.env.MODE": '"test"',
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/setup-minimal.jsx"],
    globals: true,
    testTimeout: 30000, // Increased for async component tests
    hookTimeout: 10000, // Increased for complex component rendering
    teardownTimeout: 5000, // Keep low for cleanup
    // Optimized configuration for performance
    pool: "forks",
    poolOptions: {
      forks: {
        singleFork: true,
        isolate: false, // Reuse context for better performance
      },
    },
    // Faster test execution
    minWorkers: 1,
    maxWorkers: 1, // Single worker to avoid conflicts
    // Test file patterns
    include: ["src/tests/**/*.{test,spec}.{js,jsx}"],
    exclude: ["node_modules/", "dist/", ".git/"],
    // Silence console output during tests
    silent: false,
    // Reporters configuration - use default instead of basic
    reporters: [
      [
        "default",
        {
          summary: false
        }
      ]
    ],
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});
