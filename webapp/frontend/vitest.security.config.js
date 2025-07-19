/**
 * Vitest Security Testing Configuration
 * Specialized configuration for security and vulnerability testing
 */

import { defineConfig } from 'vitest/config';
import { resolve } from 'path';

export default defineConfig({
  test: {
    // Test environment
    environment: 'jsdom',
    
    // Test patterns for security tests
    include: [
      'src/tests/security/**/*.test.{js,jsx,ts,tsx}',
      'src/tests/vulnerability/**/*.test.{js,jsx,ts,tsx}'
    ],
    
    // Security test timeout
    testTimeout: 15000,
    
    // Setup files
    setupFiles: ['src/tests/setup/security.setup.js'],
    
    // Globals for security testing
    globals: true,
    
    // Coverage for security tests
    coverage: {
      enabled: true,
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      reportsDirectory: 'coverage/security',
      include: [
        'src/utils/security/**',
        'src/services/auth/**',
        'src/utils/validation/**'
      ],
      thresholds: {
        global: {
          branches: 95,
          functions: 95,
          lines: 95,
          statements: 95
        }
      }
    },
    
    // Security-specific reporters
    reporters: ['verbose', 'json'],
    outputFile: 'test-results/security-results.json'
  },
  
  // Resolve configuration
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@tests': resolve(__dirname, 'src/tests')
    }
  },
  
  // Define for security testing
  define: {
    'process.env.NODE_ENV': '"test"',
    'process.env.VITE_SECURITY_TESTING': '"true"'
  }
});