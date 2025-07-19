/**
 * Vitest Performance Testing Configuration
 * Specialized configuration for performance and load testing
 */

import { defineConfig } from 'vitest/config';
import { resolve } from 'path';

export default defineConfig({
  test: {
    // Test environment
    environment: 'jsdom',
    
    // Test patterns for performance tests
    include: [
      'src/tests/performance/**/*.test.{js,jsx,ts,tsx}',
      'src/tests/load/**/*.test.{js,jsx,ts,tsx}'
    ],
    
    // Performance test timeout
    testTimeout: 30000,
    
    // Setup files
    setupFiles: ['src/tests/setup/performance.setup.js'],
    
    // Globals for performance testing
    globals: true,
    
    // Coverage disabled for performance tests (not meaningful)
    coverage: {
      enabled: false
    },
    
    // Performance-specific reporters
    reporters: ['verbose', 'json'],
    outputFile: 'test-results/performance-results.json',
    
    // Pool options for performance testing
    pool: 'forks',
    poolOptions: {
      forks: {
        singleFork: true // Single fork for consistent performance measurement
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
  
  // Define for performance testing
  define: {
    'process.env.NODE_ENV': '"test"',
    'process.env.VITE_PERFORMANCE_TESTING': '"true"'
  }
});