import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    // AWS CI/CD Integration Test Configuration
    name: 'aws-integration',
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup/aws-setup.js'], 
    include: [
      'src/tests/integration/aws/**/*.test.{js,jsx}',
      'src/tests/integration/workflows/**/*.test.{js,jsx}',
      'src/tests/e2e/**/*.test.{js,jsx}'
    ],
    exclude: [
      'src/tests/unit/**',
      'src/tests/integration/local/**',
      'src/tests/integration/services/liveDataService.integration.test.js',
      'src/tests/integration/services/liveDataService.realBackend.test.js'
    ],
    testTimeout: 60000, // 60 seconds for AWS tests
    hookTimeout: 30000, // 30 seconds for setup/teardown
    globals: true,
    reporter: ['verbose', 'junit'],
    outputFile: {
      junit: './test-results/aws-integration-junit.xml'
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      reportsDirectory: './coverage/aws-integration'
    },
    env: {
      NODE_ENV: 'test',
      AWS_INTEGRATION: 'true',
      SKIP_LOCAL_TESTS: 'true'
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@tests': path.resolve(__dirname, './src/tests')
    }
  }
})