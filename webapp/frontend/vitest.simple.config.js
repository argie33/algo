import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/simple-setup.js"],
    globals: true,
    testTimeout: 5000,
    hookTimeout: 5000,
    teardownTimeout: 5000,
    pool: "threads",
    poolOptions: {
      threads: {
        singleThread: true,
        isolate: false,
      },
    },
    minWorkers: 1,
    maxWorkers: 1,
    fileParallelism: false,
    silent: false,
    reporters: ["default"],
    retry: 0,
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
});