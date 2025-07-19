import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    name: 'integration',
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup.js'],
    include: [
      'src/tests/integration/**/*.test.{js,jsx}',
      'src/tests/integration/**/*.spec.{js,jsx}'
    ],
    exclude: [
      'src/tests/unit/**',
      'src/tests/e2e/**',
      'node_modules/**'
    ],
    globals: true,
    testTimeout: 30000, // 30 seconds for integration tests
    hookTimeout: 30000,
    teardownTimeout: 30000,
    // Configure coverage for integration tests
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      reportsDirectory: './test-results/integration-coverage',
      include: [
        'src/**/*.{js,jsx}',
        '!src/tests/**',
        '!src/**/*.test.{js,jsx}',
        '!src/**/*.spec.{js,jsx}'
      ],
      thresholds: {
        functions: 60,
        lines: 60,
        statements: 60,
        branches: 50
      }
    },
    // Separate output for integration tests
    outputFile: {
      junit: './test-results/integration-junit.xml'
    },
    reporter: ['verbose', 'junit'],
    // Retry flaky integration tests
    retry: 2,
    // Run integration tests sequentially for stability
    pool: 'forks',
    poolOptions: {
      forks: {
        singleFork: true
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@tests': resolve(__dirname, 'src/tests')
    }
  },
  define: {
    global: 'globalThis',
  }
})