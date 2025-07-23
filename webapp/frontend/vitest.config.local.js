import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    // Local Development Test Configuration
    name: 'local-development',
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup.js'],
    include: [
      'src/tests/unit/**/*.test.{js,jsx}',
      'src/tests/integration/simple-integration.test.js',
      'src/tests/integration/validation-real-calculations.test.js',
      'src/tests/integration/crypto-signals-aws-routes.test.js',
      'src/tests/integration/market-aws-routes.test.js',
      'src/tests/integration/dashboard-usesimplefetch.test.jsx'
    ],
    exclude: [
      'src/tests/integration/services/liveDataService.integration.test.js',
      'src/tests/integration/services/liveDataService.realBackend.test.js',
      'src/tests/integration/external/**',
      'src/tests/integration/aws/**/*.test.js',
      'src/tests/integration/workflows/**',
      'src/tests/e2e/**'
    ],
    testTimeout: 15000, // 15 seconds for local tests
    hookTimeout: 10000, // 10 seconds for setup/teardown
    globals: true,
    reporter: ['verbose', 'json'],
    outputFile: {
      json: './test-results/local-results.json'
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary'],
      reportsDirectory: './coverage/local'
    },
    env: {
      NODE_ENV: 'test',
      LOCAL_DEVELOPMENT: 'true',
      SKIP_AWS_TESTS: 'true'
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@tests': path.resolve(__dirname, './src/tests')
    }
  }
})