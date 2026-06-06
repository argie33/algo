import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.js"],
    globals: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      exclude: [
        "node_modules/",
        "src/tests/",
        "*.config.js",
        "dist/",
      ],
    },
    include: ["src/**/*.{test,spec}.{js,jsx}"],
    testTimeout: 10000,
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "aws-amplify": resolve(__dirname, "src/aws-amplify-mock"),
      "aws-amplify/auth": resolve(__dirname, "src/aws-amplify-mock/auth"),
      "@mui/material/styles": resolve(__dirname, "node_modules/@mui/material/styles/index.js"),
    },
    conditions: ["import", "require", "default"],
  },
});
