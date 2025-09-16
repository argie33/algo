import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.DEV": true,
    "import.meta.env.PROD": false,
    "import.meta.env.MODE": '"test"',
    "__DEV__": true,
    "process.env.NODE_ENV": '"test"'
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/simple-setup.js"],
    globals: true,
    testTimeout: 15000,
    hookTimeout: 10000,
    teardownTimeout: 5000,
    pool: "threads",
    poolOptions: {
      threads: {
        singleThread: true,
        minThreads: 1,
        maxThreads: 1,
      },
    },
    // Allow targeting specific files
    exclude: ["node_modules/", "dist/", ".git/", "**/*.backup", "**/*.old", "**/backup/**"],
    silent: false,
    env: {
      NODE_ENV: 'test',
    },
    reporters: ["default"],
    fileParallelism: false,
    retry: 0,
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