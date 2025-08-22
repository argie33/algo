import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.js"],
    globals: true,
    testTimeout: 30000, // Increased for real site testing
    hookTimeout: 15000,
    teardownTimeout: 10000,
    // Disable isolation for better performance
    isolate: false,
    // Pool options for better performance
    pool: "threads",
    poolOptions: {
      threads: {
        singleThread: true, // Prevent race conditions
      },
    },
    // Reporter configuration
    reporter: ["default"],
    // Coverage configuration
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      exclude: [
        "node_modules/",
        "src/tests/",
        "**/*.test.{js,jsx}",
        "**/*.spec.{js,jsx}",
      ],
    },
    // Test file patterns
    include: ["src/tests/**/*.{test,spec}.{js,jsx}"],
    exclude: ["node_modules/", "dist/", ".git/"],
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});
