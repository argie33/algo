/**
 * Vitest E2E Testing Configuration
 * Configuration for end-to-end workflow testing using Vitest
 */

import { defineConfig } from 'vitest/config';
import { resolve } from 'path';

export default defineConfig({
  test: {
    // Test environment for E2E
    environment: 'jsdom',
    
    // Test patterns for E2E tests
    include: [
      'src/tests/e2e/**/*.test.{js,jsx,ts,tsx}',
      'src/tests/integration/**/*.test.{js,jsx,ts,tsx}'
    ],
    
    // E2E test timeout (longer for complex workflows)
    testTimeout: 60000,
    
    // Setup files
    setupFiles: ['src/tests/setup/e2e.setup.js'],
    
    // Globals for E2E testing
    globals: true,
    
    // Coverage for E2E tests (workflow coverage)
    coverage: {
      enabled: true,
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      reportsDirectory: 'coverage/e2e',
      include: [
        'src/pages/**',
        'src/components/**',
        'src/services/**'
      ],
      exclude: [
        'src/tests/**',
        'src/**/*.test.{js,jsx,ts,tsx}',
        'src/**/*.stories.{js,jsx,ts,tsx}'
      ]
    },
    
    // E2E-specific reporters
    reporters: ['verbose', 'json'],
    outputFile: 'test-results/e2e-results.json',
    
    // Sequential execution for E2E tests
    pool: 'forks',
    poolOptions: {
      forks: {
        singleFork: true
      }
    }
  },
  
  // Resolve configuration
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@tests': resolve(__dirname, 'src/tests')
    }
  },
  
  // Define for E2E testing
  define: {
    'process.env.NODE_ENV': '"test"',
    'process.env.VITE_E2E_TESTING': '"true"'
  }
});